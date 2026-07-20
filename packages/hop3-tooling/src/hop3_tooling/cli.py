# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""`hop3-tools` — maintainer & operator CLI (ADR 057)."""

from __future__ import annotations

from pathlib import Path

import click

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


if __name__ == "__main__":
    main()
