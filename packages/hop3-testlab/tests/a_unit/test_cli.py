# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The `run` CLI maps args to the worker call (composition vs local suite)."""

from __future__ import annotations

import os

import pytest

from hop3_testlab import cli, worker


def _capture_run_once(monkeypatch):
    seen: dict = {}

    def _stub(target, **kw):
        seen["target"] = target
        seen.update(kw)
        return True

    monkeypatch.setattr(worker, "run_once", _stub)
    return seen


def _args(argv):
    return cli._build_parser().parse_args(argv)


def test_run_composition_maps_source_and_platform_ref(monkeypatch):
    seen = _capture_run_once(monkeypatch)
    cli._run(
        _args([
            "run",
            "coverage",
            "apps/test-apps-procfile/*",
            "--source-ref",
            "devel",
            "--platform-ref",
            "main",
            "--target",
            "docker",
        ])
    )
    assert seen["mode"] == "coverage"
    spec = seen["spec"]
    assert spec.selector == "apps/test-apps-procfile/*"  # literal, resolved server-side
    assert spec.source_ref == "devel"
    assert spec.platform_ref == "main"
    assert spec.source.name == "main-repo"  # default source label
    assert spec.apps is None  # composition: run_once resolves the selector itself


def test_run_full_suite_maps_mode_only(monkeypatch):
    seen = _capture_run_once(monkeypatch)
    cli._run(_args(["run", "ci", "--target", "docker"]))
    assert seen["mode"] == "ci"
    spec = seen["spec"]
    assert spec.source is None
    assert spec.source_ref is None
    assert spec.apps is None  # full mode suite, local checkout


def test_quoted_selector_survives_as_a_literal():
    # The shell quotes the glob; argparse keeps it intact (we expand it ourselves).
    args = _args(["run", "coverage", "apps/test-apps-procfile/*"])
    assert args.selector == "apps/test-apps-procfile/*"


def test_run_busy_exits_nonzero(monkeypatch):
    monkeypatch.setattr(worker, "run_once", lambda *a, **k: False)
    with pytest.raises(SystemExit):
        cli._run(_args(["run", "ci"]))


def test_latest_log_picks_newest(tmp_path):
    assert cli._latest_log(tmp_path / "absent") is None  # no dir
    assert cli._latest_log(tmp_path) is None  # dir, no logs
    old = tmp_path / "a.log"
    old.write_text("old")
    new = tmp_path / "b.log"
    new.write_text("new")
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))  # b is newer
    assert cli._latest_log(tmp_path).name == "b.log"
