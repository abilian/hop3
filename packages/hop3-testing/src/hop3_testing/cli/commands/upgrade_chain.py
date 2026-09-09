# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
`hop3-test upgrade-chain` — install version A on a FRESH box, then upgrade
in-place through a chain of releases, using each version's OWN installer.

Each hop is a git ref (a release tag, or `local` for the current tree). The hop
is deployed by checking that ref out into a git worktree and running THAT
checkout's `hop3-deploy-server` (via `uv run`) with the stable `--local` flag —
so every version is installed/upgraded by its own tooling, exactly as a real
operator would. Hop 1 is a clean install; every later hop is a non-clean
redeploy that hits the deployer's in-place update path (db:upgrade -> restart ->
verify). After each hop we assert the server answers (the deploy verified it)
and the schema is readable.

Runs on a FRESH box only: a local Docker container (`--docker`) or a Hetzner VPS
rebuilt for the run (`--provider hetzner`). `--host` targets an existing server
and is accepted with a warning (not a clean slate).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click
import tomllib

from hop3_testing.system_tests.provision import provision_server
from hop3_testing.targets import (
    DeploymentConfig,
    DockerConfig,
    DockerTarget,
    RemoteConfig,
    RemoteTarget,
)

# 0.6.0's rootd is broken (imports __version__ that its __init__ never defines),
# so 0.6.2 is the first viable baseline. Extend as releases land. The last hop
# is `local` so the chain exercises THIS checkout's deployer: a release tag as
# the last hop tests the deployer that shipped with that tag, fixes since
# excluded.
DEFAULT_CHAIN = "0.6.2,local"

_CONTAINER = "hop3-upgrade-chain"
#: The interpreter every hop's worktree runs under. A tag's worktree carries no
#: `.python-version`, so a bare `uv run` there picks the newest interpreter on
#: the machine; on a Mac with 3.14 free-threaded installed that resolved a
#: dependency (psycopg-binary) with no wheel for it and the chain died before
#: touching the target. Pin to the interpreter this process runs on.
_PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"
_HOP3_SERVER = "/home/hop3/venv/bin/hop3-server"
_HOP3_PYTHON = "/home/hop3/venv/bin/python"


def _deployer_script(checkout: Path) -> str:
    """
    The deployer's console-script name in this checkout, from its pyproject.

    It was `hop3-deploy` before 0.7.0 and `hop3-deploy-server` after. Asking
    for the wrong name is not an error to `uv run`: it falls through to PATH
    and runs the developer's own (current) deployer, which is how a chain once
    reported a fresh 0.6.2 install that had 0.7.3 on the box.
    """
    pyproject = checkout / "packages" / "hop3-installer" / "pyproject.toml"
    scripts = tomllib.loads(pyproject.read_text()).get("project", {}).get("scripts", {})
    names = [
        n for n, target in scripts.items() if target == "hop3_installer.deployer:main"
    ]
    if len(names) != 1:
        msg = (
            f"{pyproject}: expected one script targeting "
            f"hop3_installer.deployer:main, found {names}"
        )
        raise RuntimeError(msg)
    return names[0]


def _server_version(checkout: Path) -> str:
    """The hop3-server version this checkout would install."""
    pyproject = checkout / "packages" / "hop3-server" / "pyproject.toml"
    return tomllib.loads(pyproject.read_text())["project"]["version"]


def _sync_checkout(checkout: Path, script: str) -> None:
    """
    Build the checkout's own environment and prove its deployer is in it.

    `uv run` would sync on its own, but it would also fall back to PATH for a
    script the environment lacks; syncing first and checking the script exists
    turns that silent fallback into a failure here.
    """
    subprocess.run(
        ["uv", "sync", "--python", _PYTHON],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    )
    if not (checkout / ".venv" / "bin" / script).exists():
        msg = f"{checkout}: `uv sync` did not produce .venv/bin/{script}"
        raise RuntimeError(msg)


def _hop_config(
    *, cwd: Path, script: str, clean: bool, verbose: bool
) -> DeploymentConfig:
    """
    A deploy config that runs the checkout-at-``cwd``'s own deployer.

    ``command_prefix=["uv", "run", "--python", …]`` + ``cwd`` run that ref's
    hop3-deploy-server on this process's interpreter;
    ``legacy_flags`` emits ``--local`` (which every version accepts).
    """
    return DeploymentConfig(
        source="local",
        clean=clean,
        verbose=verbose,
        command_prefix=["uv", "run", "--python", _PYTHON],
        cwd=cwd,
        deployer_command=script,
        legacy_flags=True,
    )


def _checkout(ref: str, repo_root: Path, tmp: Path, worktrees: list[Path]) -> Path:
    """
    Return a source tree for ``ref``: the repo itself for ``local``, else a
    git worktree checked out at that tag (recorded for cleanup).
    """
    if ref == "local":
        return repo_root
    dest = tmp / ref.replace("/", "_")
    subprocess.run(
        ["git", "-C", str(repo_root), "worktree", "add", "--detach", str(dest), ref],
        check=True,
        capture_output=True,
        text=True,
    )
    worktrees.append(dest)
    return dest


@click.command("upgrade-chain")
@click.option(
    "--docker",
    "target_type",
    flag_value="docker",
    help="Run the chain in a fresh local Docker container.",
)
@click.option(
    "--host",
    envvar="HOP3_HOST",
    default=None,
    help="Existing server (NOT a clean slate — prefer --docker/--provider).",
)
@click.option("--provider", default=None, help="Rebuild a fresh cloud VPS (hetzner).")
@click.option(
    "--server-id",
    type=int,
    envvar="HETZNER_SERVER_ID",
    default=None,
    help="Cloud server ID to rebuild for --provider (or $HETZNER_SERVER_ID).",
)
@click.option(
    "--image", default=None, help="OS image for --provider (e.g. ubuntu-24.04)."
)
@click.option("--port", type=int, default=22, help="SSH port.")
@click.option("--user", default="root", help="SSH user.")
@click.option(
    "--identity",
    "--ssh-key",
    "ssh_key",
    envvar="HOP3_SSH_KEY",
    default=None,
    help="SSH private key path (default: $HOP3_SSH_KEY).",
)
@click.option(
    "--chain",
    default=DEFAULT_CHAIN,
    help=f"Comma-separated git refs (default: {DEFAULT_CHAIN}). "
    "Each is a release tag (e.g. 0.6.2) or `local` for the current tree.",
)
@click.option("--keep", is_flag=True, help="Keep the target + worktrees after the run.")
@click.pass_context
def upgrade_chain(
    ctx: click.Context,
    target_type: str | None,
    host: str | None,
    provider: str | None,
    server_id: int | None,
    image: str | None,
    port: int,
    user: str,
    ssh_key: str | None,
    chain: str,
    keep: bool,
) -> None:
    """Install version A on a fresh box, then upgrade through a version chain."""
    verbose = bool(ctx.obj.get("verbose")) if ctx.obj else False
    root = ctx.obj.get("root") if ctx.obj else None
    repo_root = Path(root) if root else Path.cwd()

    refs = [r.strip() for r in chain.split(",") if r.strip()]
    if len(refs) < 2:
        msg = "--chain needs at least two hops: an install and one upgrade."
        raise click.UsageError(msg)

    is_docker = target_type == "docker"
    if provider:
        host = provision_server(
            provider=provider, server_id=server_id, image=image, verbose=verbose
        )
        click.echo(f"Provisioned fresh {provider} server: {host}")
    if not is_docker and not host:
        msg = "Choose a fresh target: --docker, --provider hetzner, or --host <server>."
        raise click.UsageError(msg)
    if host and not provider and not is_docker:
        click.echo(
            "⚠ --host is an EXISTING server, not a clean slate; the chain assumes "
            "a fresh box. Prefer --docker or --provider hetzner.",
            err=True,
        )

    target: DockerTarget | RemoteTarget | None = None
    worktrees: list[Path] = []
    tmp = Path(tempfile.mkdtemp(prefix="hop3-upgrade-chain-"))
    results: list[dict[str, str]] = []
    try:
        checkouts = [_checkout(ref, repo_root, tmp, worktrees) for ref in refs]
        scripts = [_deployer_script(c) for c in checkouts]
        versions = [_server_version(c) for c in checkouts]
        for checkout, script in zip(checkouts, scripts, strict=True):
            if checkout == repo_root:
                # `local` is the developer's own environment: never sync it
                # (uv would drop the extras they installed), only check it.
                if not (checkout / ".venv" / "bin" / script).exists():
                    msg = f"{checkout}: .venv/bin/{script} is missing; run `uv sync`"
                    raise RuntimeError(msg)
                continue
            _sync_checkout(checkout, script)

        target = _make_target(
            is_docker,
            host,
            port,
            user,
            ssh_key,
            _hop_config(
                cwd=checkouts[0], script=scripts[0], clean=True, verbose=verbose
            ),
        )
        click.echo(
            f"\n=== hop 1/{len(refs)}: fresh install {refs[0]} ({scripts[0]}) ==="
        )
        target.start()
        results.append(_assert_hop(target, refs[0], versions[0]))

        for i, ref in enumerate(refs[1:], start=2):
            click.echo(
                f"\n=== hop {i}/{len(refs)}: upgrade to {ref} ({scripts[i - 1]}) ==="
            )
            target.redeploy(
                _hop_config(
                    cwd=checkouts[i - 1],
                    script=scripts[i - 1],
                    clean=False,
                    verbose=verbose,
                )
            )
            results.append(_assert_hop(target, ref, versions[i - 1]))
    except Exception as exc:  # a failed hop -> loud summary + nonzero exit
        _print_summary(results)
        click.echo(f"\n✗ Upgrade chain FAILED: {exc}", err=True)
        _cleanup(target, worktrees, tmp, repo_root, keep=keep)
        ctx.exit(1)

    _print_summary(results)
    _cleanup(target, worktrees, tmp, repo_root, keep=keep)
    click.echo(f"\n✓ Upgrade chain passed: {' → '.join(refs)}")


def _make_target(is_docker, host, port, user, ssh_key, deployment):
    """Build the fresh-box target for hop 1 (Docker container or SSH host)."""
    if is_docker:
        return DockerTarget(
            DockerConfig(container_name=_CONTAINER), deployment=deployment
        )
    return RemoteTarget(
        RemoteConfig(host=host, port=port, user=user, ssh_key=ssh_key),
        deployment=deployment,
    )


def _assert_hop(target, ref: str, expected_version: str) -> dict[str, str]:
    """
    Assert the box is healthy at this hop; return {version, rootd, revision}.

    The deploy already health-verified the server (start/redeploy raise
    otherwise); this adds: the installed version is the one this hop's checkout
    carries (the wrong deployer running is otherwise invisible), hop3-rootd is
    at that same version (every update path used to leave the daemon behind),
    and the schema is stamped + readable (`db:current`).
    """
    version = _exec(
        target,
        f'{_HOP3_PYTHON} -c "import importlib.metadata as m;'
        " print(m.version('hop3_server'))\"",
    )
    if version != expected_version:
        msg = (
            f"after hop {ref} the box runs hop3-server {version}, expected "
            f"{expected_version}: a different checkout's deployer ran"
        )
        raise RuntimeError(msg)
    rootd = _exec(
        target,
        f'{_HOP3_PYTHON} -c "import importlib.metadata as m;'
        " print(m.version('hop3_rootd'))\"",
    )
    if rootd != expected_version:
        msg = (
            f"after hop {ref} the box runs hop3-rootd {rootd} beside hop3-server "
            f"{version}: the update path left the daemon behind"
        )
        raise RuntimeError(msg)
    rc, rev_out, rev_err = target.exec_run(f"sudo -u hop3 {_HOP3_SERVER} db:current")
    revision = (rev_out or "").strip()
    if rc != 0 or not revision:
        detail = (rev_err or rev_out or "").strip()
        msg = f"db:current failed after {ref}: {detail!r}"
        raise RuntimeError(msg)

    click.echo(f"  ✓ {ref}: version={version} rootd={rootd} schema={revision}")
    return {"hop": ref, "version": version, "rootd": rootd, "revision": revision}


def _exec(target, command: str) -> str:
    """Run a shell command on the target as the hop3 user; return stdout."""
    rc, out, err = target.exec_run(f"sudo -u hop3 {command}")
    if rc != 0:
        msg = f"command failed (rc={rc}): {command}\n{(err or out).strip()}"
        raise RuntimeError(msg)
    return (out or "").strip()


def _cleanup(
    target, worktrees: list[Path], tmp: Path, repo_root: Path, *, keep: bool
) -> None:
    if keep:
        click.echo(f"\n--keep: target left running; worktrees under {tmp}")
        return
    if target is not None:
        target.stop()
    for wt in worktrees:
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(wt)],
            check=False,
            capture_output=True,
        )
    shutil.rmtree(tmp, ignore_errors=True)


def _print_summary(results: list[dict[str, str]]) -> None:
    if not results:
        return
    click.echo("\nUpgrade chain:")
    for r in results:
        click.echo(
            f"  {r['hop']:>12}  version={r['version']:<10} "
            f"rootd={r['rootd']:<10} schema={r['revision']}"
        )
