# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""``hop3-test why <run-id>`` — replay a saved diagnostic bundle (ADR 043 §7)."""

from __future__ import annotations

import json
from pathlib import Path

import click

from hop3_testing.bundle_ids import DEFAULT_RUNS_DIR
from hop3_testing.results import ResultStore

# CLI section flags -> on-disk file. `proxy` maps to proxy_probe.txt.
_SECTIONS = ["proxy", "nginx", "app", "journal", "build", "deploy", "http", "dns"]
_FILE = {"proxy": "proxy_probe.txt", **{s: f"{s}.txt" for s in _SECTIONS[1:]}}


def _resolve_bundle(run_id: str) -> tuple[Path, str | None, str | None] | None:
    """
    Locate a bundle by run-id: the store record first, else the on-disk dir.

    A diagnostic bundle is written to ``~/.hop3/test-runs/<run-id>/`` even when
    no result row exists yet — a deploy/startup failure is captured before any
    ``TestResult`` (see ``_emit_startup_diagnostics``). The failure headline
    still prints ``hop3-test why <run-id>``, so that pointer has to resolve
    off-disk too, or the tool contradicts itself: "diagnostics saved … run
    `why`" followed by "No bundle found".

    Returns ``(bundle_dir, headline, classification)``, or None when nothing is
    found. The run-id printed in a headline is the final directory basename
    (``write_bundle`` guarantees it), so the on-disk path is exact for the id
    the user was told to use.
    """
    record = ResultStore().get_result_by_run_id(run_id)
    if record is not None and record.bundle_path:
        return Path(str(record.bundle_path)), record.headline, record.classification

    # No store record — fall back to the on-disk bundle and its manifest. Guard
    # against a run-id that isn't a bare basename (no path traversal).
    if Path(run_id).name != run_id:
        return None
    bundle_dir = DEFAULT_RUNS_DIR / run_id
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        manifest = {}
    return bundle_dir, manifest.get("headline"), manifest.get("classifier")


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
    """
    Show the diagnostic bundle for a failed run.

    RUN_ID is the ``<ISO>-<app>-<shortid>`` printed in a failure headline. The
    bundle resolves from the result store, or — when the failure had no result
    row (e.g. a deploy that never came up) — directly from its on-disk directory.
    """
    resolved = _resolve_bundle(run_id)
    if resolved is None:
        msg = f"No bundle found for run-id {run_id!r}"
        raise click.ClickException(msg)
    bundle_dir, headline, classification = resolved

    if list_sections:
        if not bundle_dir.exists():
            msg = f"Bundle directory is gone: {bundle_dir}"
            raise click.ClickException(msg)
        for f in sorted(bundle_dir.glob("*.txt")):
            click.echo(f.stem)
        return

    if section is None:
        click.echo(headline or "(no headline)")
        click.echo(f"classification: {classification}")
        click.echo(f"bundle: {bundle_dir}")
        return

    path = bundle_dir / _FILE[section]
    if not path.exists():
        msg = f"Section {section!r} not in bundle ({path})"
        raise click.ClickException(msg)
    click.echo(path.read_text())
