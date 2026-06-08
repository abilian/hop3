# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""``hop3-test why <run-id>`` — replay a saved diagnostic bundle (ADR 043 §7)."""

from __future__ import annotations

from pathlib import Path

import click

from hop3_testing.results import ResultStore

# CLI section flags -> on-disk file. `proxy` maps to proxy_probe.txt.
_SECTIONS = ["proxy", "nginx", "app", "journal", "build", "deploy", "http", "dns"]
_FILE = {"proxy": "proxy_probe.txt", **{s: f"{s}.txt" for s in _SECTIONS[1:]}}


@click.command("why")
@click.argument("run_id")
@click.option(
    "--section",
    type=click.Choice(_SECTIONS),
    default=None,
    help="Replay one section from the saved bundle.",
)
@click.option("--list", "list_sections", is_flag=True, help="List available sections.")
def why_cmd(run_id: str, section: str | None, *, list_sections: bool) -> None:
    """Show the diagnostic bundle for a failed run.

    RUN_ID is the ``<ISO>-<app>-<shortid>`` printed in a failure headline.
    """
    store = ResultStore()
    record = store.get_result_by_run_id(run_id)
    if record is None or not record.bundle_path:
        msg = f"No bundle found for run-id {run_id!r}"
        raise click.ClickException(msg)

    bundle_dir = Path(str(record.bundle_path))

    if list_sections:
        if not bundle_dir.exists():
            msg = f"Bundle directory is gone: {bundle_dir}"
            raise click.ClickException(msg)
        for f in sorted(bundle_dir.glob("*.txt")):
            click.echo(f.stem)
        return

    if section is None:
        click.echo(record.headline or "(no headline)")
        click.echo(f"classification: {record.classification}")
        click.echo(f"bundle: {bundle_dir}")
        return

    path = bundle_dir / _FILE[section]
    if not path.exists():
        msg = f"Section {section!r} not in bundle ({path})"
        raise click.ClickException(msg)
    click.echo(path.read_text())
