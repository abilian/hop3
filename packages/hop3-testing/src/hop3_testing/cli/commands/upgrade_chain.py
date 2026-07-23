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
import tempfile
from pathlib import Path

import click

from hop3_testing.system_tests.provision import provision_server
from hop3_testing.targets import (
    DeploymentConfig,
    DockerConfig,
    DockerTarget,
    RemoteConfig,
    RemoteTarget,
)

# 0.6.0's rootd is broken (imports __version__ that its __init__ never defines),
# so 0.6.2 is the first viable baseline. Extend as releases land.
DEFAULT_CHAIN = "0.6.2,local"

_CONTAINER = "hop3-upgrade-chain"
_HOP3_SERVER = "/home/hop3/venv/bin/hop3-server"
_HOP3_PYTHON = "/home/hop3/venv/bin/python"


def _hop_config(*, cwd: Path, clean: bool, verbose: bool) -> DeploymentConfig:
    """
    A deploy config that runs the checkout-at-``cwd``'s own deployer.

    ``command_prefix=["uv", "run"]`` + ``cwd`` run that ref's hop3-deploy-server;
    ``legacy_flags`` emits ``--local`` (which every version accepts).
    """
    return DeploymentConfig(
        source="local",
        clean=clean,
        verbose=verbose,
        command_prefix=["uv", "run"],
        cwd=cwd,
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

        target = _make_target(
            is_docker,
            host,
            port,
            user,
            ssh_key,
            _hop_config(cwd=checkouts[0], clean=True, verbose=verbose),
        )
        click.echo(f"\n=== hop 1/{len(refs)}: fresh install {refs[0]} ===")
        target.start()
        results.append(_assert_hop(target, refs[0]))

        for i, ref in enumerate(refs[1:], start=2):
            click.echo(f"\n=== hop {i}/{len(refs)}: upgrade to {ref} ===")
            target.redeploy(
                _hop_config(cwd=checkouts[i - 1], clean=False, verbose=verbose)
            )
            results.append(_assert_hop(target, ref))
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


def _assert_hop(target, ref: str) -> dict[str, str]:
    """
    Assert the box is healthy at this hop; return {version, revision}.

    The deploy already health-verified the server (start/redeploy raise
    otherwise); this adds: the installed version is readable, and the schema is
    stamped + readable (`db:current`).
    """
    version = _exec(
        target,
        f'{_HOP3_PYTHON} -c "import importlib.metadata as m;'
        " print(m.version('hop3_server'))\"",
    )
    rc, rev_out, rev_err = target.exec_run(f"sudo -u hop3 {_HOP3_SERVER} db:current")
    revision = (rev_out or "").strip()
    if rc != 0 or not revision:
        detail = (rev_err or rev_out or "").strip()
        msg = f"db:current failed after {ref}: {detail!r}"
        raise RuntimeError(msg)

    click.echo(f"  ✓ {ref}: version={version} schema={revision}")
    return {"hop": ref, "version": version, "revision": revision}


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
            f"  {r['hop']:>12}  version={r['version']:<16} schema={r['revision']}"
        )
