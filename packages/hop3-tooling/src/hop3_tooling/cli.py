# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""`hop3-tools` — maintainer & operator CLI (ADR 057)."""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import click
import tomllib

if TYPE_CHECKING:
    from collections.abc import Iterator

from hop3.plugins.build.nix.gen.registry import generate
from hop3.plugins.build.nix.gen.toml_adapter import app_spec_from_config
from hop3_tooling.nix_hash import (
    PLACEHOLDER_HASH,
    hash_key_for,
    parse_nix_hash_mismatch,
    set_nix_hash,
)
from hop3_tooling.nix_repro import ReproResult, interpret_rebuild, summarize

from . import catalog as catalog_lib
from .verify import CHECKS, DEFAULT_HOST, run_verification


@click.group()
@click.version_option(package_name="hop3-tooling")
def main() -> None:
    """Hop3 maintainer & operator tooling (ADR 057)."""


@main.group()
def catalog() -> None:
    """Catalog tooling: keep the catalog identical to its tested source."""


@catalog.command()
@click.option(
    "--catalog-apps",
    type=click.Path(path_type=Path),
    default=None,
    help="catalog apps/ dir (default: sibling hop3-catalog checkout)",
)
@click.option(
    "--source-root",
    type=click.Path(path_type=Path),
    default=None,
    help="tested-source variant root (default: apps/real-apps-native)",
)
def drift(catalog_apps: Path | None, source_root: Path | None) -> None:
    """Fail if any catalog recipe differs from its tested source (CI gate).

    Compares each app's hop3.toml + scripts/ byte-for-byte, ignoring the
    catalog-only overlay (catalog.toml, readme*, icons, screenshots/).
    """
    catalog_apps = catalog_apps or catalog_lib.default_catalog_apps()
    source_root = source_root or catalog_lib.default_source_root()
    if not catalog_apps.is_dir():
        msg = f"catalog apps dir not found: {catalog_apps}"
        raise click.ClickException(msg)

    click.echo(f"Catalog: {catalog_apps}")
    click.echo(f"Source:  {source_root}\n")

    ids = catalog_lib.app_ids(catalog_apps)
    bad = 0
    for app_id in ids:
        issues = catalog_lib.compare_app(catalog_apps / app_id, source_root / app_id)
        if not issues:
            click.echo(f"  OK     {app_id}")
        else:
            bad += 1
            click.echo(f"  DRIFT  {app_id}")
            for issue in issues:
                click.echo(f"           - {issue}")

    click.echo("")
    if bad:
        click.echo(
            f"DRIFT: {bad} of {len(ids)} catalog app(s) differ from tested source."
        )
        click.echo("Re-promote from the tested source (do not hand-edit the catalog).")
        raise SystemExit(1)
    click.echo(f"All {len(ids)} catalog app(s) match their tested source.")


@catalog.command()
@click.argument("apps", nargs=-1)
@click.option("--all", "all_", is_flag=True, help="promote every catalog app")
@click.option("--catalog-apps", type=click.Path(path_type=Path), default=None)
@click.option("--source-root", type=click.Path(path_type=Path), default=None)
def promote(
    apps: tuple[str, ...],
    all_: bool,
    catalog_apps: Path | None,
    source_root: Path | None,
) -> None:
    """Copy tested recipe(s) into the catalog verbatim (overlay untouched).

    Replaces each app's hop3.toml + scripts/ from apps/real-apps-native/<app>/.
    Pass app ids, or --all. Run `hop3-tools catalog drift` afterwards to confirm.
    """
    catalog_apps = catalog_apps or catalog_lib.default_catalog_apps()
    source_root = source_root or catalog_lib.default_source_root()
    if not catalog_apps.is_dir():
        msg = f"catalog apps dir not found: {catalog_apps}"
        raise click.ClickException(msg)

    targets = catalog_lib.app_ids(catalog_apps) if all_ else list(apps)
    if not targets:
        msg = "name at least one app, or pass --all"
        raise click.ClickException(msg)

    for app_id in targets:
        try:
            catalog_lib.promote_app(app_id, source_root, catalog_apps)
        except FileNotFoundError as e:
            raise click.ClickException(str(e)) from e
        click.echo(f"  promoted {app_id}")
    click.echo(f"\nPromoted {len(targets)} app(s). Now run: hop3-tools catalog drift")


@catalog.command()
@click.option(
    "--apps", default="", help="comma-separated subset (default: all verifiable)"
)
@click.option(
    "--host", default=DEFAULT_HOST, help="box hostname (SSH DB check + label)"
)
@click.option(
    "--deploy", "do_deploy", is_flag=True, help="catalog-install each app first"
)
@click.option("--cleanup", is_flag=True, help="with --deploy, destroy each app after")
@click.option("--insecure", is_flag=True, help="skip TLS verification (dev box)")
@click.option("--name-map", default="", help="id=deployed_name,... overrides")
def verify(
    apps: str,
    host: str,
    do_deploy: bool,
    cleanup: bool,
    insecure: bool,
    name_map: str,
) -> None:
    """Install catalog apps and functionally verify their admin bootstrap.

    Asserts (per app) that the old default credential is rejected, the generated
    one works, and registration/anonymous access is closed. Not a bare 200.
    """
    selected = [a.strip() for a in apps.split(",") if a.strip()] or list(CHECKS)
    unknown = [a for a in selected if a not in CHECKS]
    if unknown:
        msg = f"unknown app(s): {unknown}. Known: {sorted(CHECKS)}"
        raise click.ClickException(msg)
    mapping = dict(kv.split("=", 1) for kv in name_map.split(",") if "=" in kv)

    ok = run_verification(
        selected,
        host=host,
        do_deploy=do_deploy,
        cleanup=cleanup,
        insecure=insecure,
        name_map=mapping,
    )
    raise SystemExit(0 if ok else 1)


@main.group()
def nix() -> None:
    """Nix-recipe maintenance."""


def _ssh_base(host: str) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        f"root@{host}",
    ]


def _scp_dir(app_dir: Path, host: str, remote_dir: str) -> None:
    subprocess.run(
        [
            "scp",
            "-q",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-r",
            f"{app_dir}/.",
            f"root@{host}:{remote_dir}/",
        ],
        check=True,
    )


def _build_locally(nix_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["nix", "build", "--no-link", "-f", str(nix_file), "package"],
        capture_output=True,
        text=True,
        check=False,
    )


def _build_over_ssh(app_dir: Path, host: str) -> subprocess.CompletedProcess[str]:
    """Build the recipe on a remote Linux host and return the result.

    The dependency set Nix downloads is platform-specific (a Linux wheel set is
    not a macOS one), so the hash must be computed on the platform that will
    actually run the app. The whole app directory is copied because the
    expression references its lockfiles by relative path.
    """
    remote_dir = f"/tmp/hop3-vendor-hash/{app_dir.name}"
    ssh_base = _ssh_base(host)
    subprocess.run(
        [*ssh_base, f"rm -rf {remote_dir} && mkdir -p {remote_dir}"], check=True
    )
    _scp_dir(app_dir, host, remote_dir)
    try:
        return subprocess.run(
            [
                *ssh_base,
                (
                    f"cd {remote_dir} && "
                    f"export NIX_CONFIG='experimental-features = nix-command flakes'; "
                    f"nix build --no-link -f hop3.nix package"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        subprocess.run([*ssh_base, f"rm -rf {remote_dir}"], check=False)


@nix.command("vendor-hash")
@click.argument("app_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--write/--dry-run", default=True, help="Write the hash into hop3.toml.")
@click.option(
    "--ssh",
    default=None,
    help="Build on a Linux host over SSH. Required from macOS: Nix resolves a\nplatform-specific dependency set, so a darwin build yields the wrong hash.",
)
def vendor_hash(app_dir: Path, write: bool, ssh: str | None) -> None:
    """Compute a recipe's vendored-dependency hash and record it.

    The hermetic templates pin their dependency set with a fixed-output
    derivation, whose hash can only be learned by building once. This performs
    that cycle: generate with a placeholder, build, read the hash Nix reports,
    write it back.
    """
    toml_path = app_dir / "hop3.toml"
    if not toml_path.is_file():
        msg = f"{app_dir}: no hop3.toml"
        raise click.ClickException(msg)

    config = tomllib.loads(toml_path.read_text())
    template = (config.get("nix") or {}).get("template", "")
    try:
        key = hash_key_for(template)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    # Generate with the placeholder so Nix gets far enough to report the truth.
    seeded = set_nix_hash(toml_path.read_text(), key, PLACEHOLDER_HASH)
    seeded_config = tomllib.loads(seeded)
    spec = app_spec_from_config(
        seeded_config.get("nix") or {},
        seeded_config.get("metadata") or {},
        app_dir.name,
    )
    # A recipe missing its lockfile cannot be generated at all; report that
    # as the actionable problem it is rather than a traceback.
    try:
        expression = generate(spec)
    except ValueError as exc:
        msg = f"{app_dir.name}: {exc}"
        raise click.ClickException(msg) from exc

    with _materialized_nix(app_dir, expression):
        result = (
            _build_over_ssh(app_dir, ssh)
            if ssh
            else _build_locally(app_dir / "hop3.nix")
        )

    if result.returncode == 0:
        click.echo(f"{app_dir.name}: builds with the placeholder — nothing to pin?")
        return

    found = parse_nix_hash_mismatch(result.stderr)
    if found is None:
        # Fail loud: a build that failed for another reason must not look like
        # a missing hash.
        click.echo(result.stderr.strip()[-2000:], err=True)
        msg = f"{app_dir.name}: build failed without a hash mismatch (see above)"
        raise click.ClickException(msg)

    click.echo(f"{app_dir.name}  {key} = {found}")
    if write:
        toml_path.write_text(set_nix_hash(toml_path.read_text(), key, found))
        click.echo(f"  written to {toml_path}")


@nix.command("check-reproducible")
@click.argument(
    "roots",
    nargs=-1,
    type=click.Path(exists=True, path_type=Path),
)
@click.option("--ssh", default=None, help="Build on a Linux host over SSH.")
def check_reproducible(roots: tuple[Path, ...], ssh: str | None) -> None:
    """Rebuild each nix-gen app and fail if any output is not deterministic.

    For every recipe under ROOTS, generate its ``hop3.nix``, build it, then
    ``nix build --rebuild`` (which rebuilds and compares against the first
    output). A changed output means the build is not reproducible — which is
    the whole claim the hermetic templates make. Exits non-zero on the first
    failure or an empty selection.
    """
    roots = roots or (Path("apps/real-apps-nix-gen"),)

    def _recipes(root: Path) -> list[Path]:
        # A root may be a directory of app dirs, or a single app dir itself.
        own = [root / "hop3.toml"] if (root / "hop3.toml").is_file() else []
        return own + list(root.glob("*/hop3.toml"))

    app_dirs = sorted({
        toml_file.parent
        for root in roots
        for toml_file in _recipes(root)
        if "template" in (tomllib.loads(toml_file.read_text()).get("nix") or {})
    })
    if not app_dirs:
        # A gate that found nothing to check must not look like a green run.
        msg = f"no nix-gen recipe found under {[str(r) for r in roots]}"
        raise click.ClickException(msg)

    results = []
    for app_dir in app_dirs:
        result = _rebuild_check(app_dir, ssh)
        mark = "ok " if result.reproducible else "FAIL"
        click.echo(f"  {mark} {result.app}: {result.detail}")
        results.append(result)

    ok, summary = summarize(results)
    click.echo(f"\n{summary}")
    raise SystemExit(0 if ok else 1)


def _generated_expression(app_dir: Path) -> str:
    """The hop3.nix an app's recipe generates (raises click errors on failure)."""
    config = tomllib.loads((app_dir / "hop3.toml").read_text())
    spec = app_spec_from_config(
        config.get("nix") or {},
        config.get("metadata") or {},
        app_dir.name,
    )
    try:
        return generate(spec)
    except ValueError as exc:
        msg = f"{app_dir.name}: {exc}"
        raise click.ClickException(msg) from exc


@contextmanager
def _materialized_nix(app_dir: Path, expression: str) -> Iterator[None]:
    """Write a generated hop3.nix for the duration of a build, then restore.

    hop3.nix is generated, never committed, so we must not leave one behind — a
    stray file would shadow the recipe on the next generation.
    """
    nix_file = app_dir / "hop3.nix"
    original = nix_file.read_text() if nix_file.exists() else None
    nix_file.write_text(expression)
    try:
        yield
    finally:
        if original is None:
            nix_file.unlink(missing_ok=True)
        else:
            nix_file.write_text(original)


def _rebuild_check(app_dir: Path, ssh: str | None) -> ReproResult:
    # A recipe that cannot even generate is not reproducible; report it as such
    # rather than crashing the whole gate.
    try:
        expression = _generated_expression(app_dir)
    except click.ClickException as exc:
        return ReproResult(app_dir.name, reproducible=False, detail=str(exc.message))

    with _materialized_nix(app_dir, expression):
        if ssh:
            return interpret_rebuild(
                app_dir.name, *_run(_rebuild_over_ssh(app_dir, ssh))
            )
        build = _build_locally(app_dir / "hop3.nix")
        if build.returncode != 0:
            return interpret_rebuild(app_dir.name, build.returncode, build.stderr)
        rebuild = _rebuild_locally(app_dir / "hop3.nix")
        return interpret_rebuild(app_dir.name, rebuild.returncode, rebuild.stderr)


def _run(proc: subprocess.CompletedProcess[str]) -> tuple[int, str]:
    return proc.returncode, proc.stderr


def _rebuild_locally(nix_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["nix", "build", "--rebuild", "--no-link", "-f", str(nix_file), "package"],
        capture_output=True,
        text=True,
        check=False,
    )


def _rebuild_over_ssh(app_dir: Path, host: str) -> subprocess.CompletedProcess[str]:
    remote_dir = f"/tmp/hop3-repro/{app_dir.name}"
    ssh_base = _ssh_base(host)
    subprocess.run(
        [*ssh_base, f"rm -rf {remote_dir} && mkdir -p {remote_dir}"], check=True
    )
    _scp_dir(app_dir, host, remote_dir)
    try:
        return subprocess.run(
            [
                *ssh_base,
                (
                    f"cd {remote_dir} && "
                    f"export NIX_CONFIG='experimental-features = nix-command flakes'; "
                    f"nix build --no-link -f hop3.nix package && "
                    f"nix build --rebuild --no-link -f hop3.nix package"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        subprocess.run([*ssh_base, f"rm -rf {remote_dir}"], check=False)


if __name__ == "__main__":
    main()
