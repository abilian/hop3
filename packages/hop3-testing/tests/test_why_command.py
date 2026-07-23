# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`hop3-test why <run-id>` bundle resolution — store record + on-disk fallback.

Regression: a deploy/startup failure writes a bundle to disk but no result row,
while its failure headline still prints `hop3-test why <run-id>`. That pointer
must resolve off-disk instead of the tool contradicting itself — "diagnostics
saved … run `why`" followed by "No bundle found for run-id".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from click.testing import CliRunner
from hop3_testing.bundle import Bundle, write_bundle
from hop3_testing.cli.commands import why as why_module
from hop3_testing.cli.commands.why import why_cmd

if TYPE_CHECKING:
    from pathlib import Path

_RUN_ID = "2026-07-06T17-51-48Z-startup-f2a02a"


def _write_startup_bundle(runs: Path) -> Bundle:
    """
    A startup-failure bundle written to disk with NO result row (the case
    `_emit_startup_diagnostics` produces).
    """
    bundle = Bundle(
        run_id=_RUN_ID,
        app="startup",
        target_kind="ssh",
        classifier="app-crash",
        headline=f"✗ app-crash — startup\nwhy: hop3-test why {_RUN_ID} --section app",
        sections={"app": "the app section body"},
    )
    return write_bundle(bundle, base_dir=runs)


def _empty_store(tmp_path: Path, monkeypatch, runs: Path) -> None:
    # `why_cmd` builds its own ResultStore(); point it at an empty DB (no row for
    # the run-id) and its on-disk lookup at the temp runs dir.
    monkeypatch.setenv("HOP3_TEST_RESULTS_DB", str(tmp_path / "empty.db"))
    monkeypatch.setattr(why_module, "DEFAULT_RUNS_DIR", runs)


def test_why_resolves_on_disk_bundle_without_store_record(tmp_path, monkeypatch):
    runs = tmp_path / "test-runs"
    _empty_store(tmp_path, monkeypatch, runs)
    written = _write_startup_bundle(runs)

    result = CliRunner().invoke(why_cmd, [written.run_id])

    assert result.exit_code == 0, result.output
    assert "No bundle found" not in result.output
    assert str(written.artifact_dir) in result.output  # bundle: <dir>
    assert "app-crash" in result.output  # classification from the manifest


def test_why_replays_a_section_off_disk(tmp_path, monkeypatch):
    runs = tmp_path / "test-runs"
    _empty_store(tmp_path, monkeypatch, runs)
    written = _write_startup_bundle(runs)

    result = CliRunner().invoke(why_cmd, [written.run_id, "--section", "app"])

    assert result.exit_code == 0, result.output
    assert "the app section body" in result.output


def test_why_lists_sections_off_disk(tmp_path, monkeypatch):
    runs = tmp_path / "test-runs"
    _empty_store(tmp_path, monkeypatch, runs)
    written = _write_startup_bundle(runs)

    result = CliRunner().invoke(why_cmd, [written.run_id, "--list"])

    assert result.exit_code == 0, result.output
    assert "app" in result.output.split()


def test_why_still_reports_missing_when_nothing_on_disk(tmp_path, monkeypatch):
    runs = tmp_path / "test-runs"
    _empty_store(tmp_path, monkeypatch, runs)
    # No bundle written anywhere.
    result = CliRunner().invoke(why_cmd, ["2026-01-01T00-00-00Z-nope-000000"])

    assert result.exit_code != 0
    assert "No bundle found" in result.output


def test_why_rejects_path_traversal_run_id(tmp_path, monkeypatch):
    runs = tmp_path / "test-runs"
    _empty_store(tmp_path, monkeypatch, runs)
    result = CliRunner().invoke(why_cmd, ["../../etc/passwd"])

    assert result.exit_code != 0
    assert "No bundle found" in result.output
