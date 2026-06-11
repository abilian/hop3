# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The meta runner must surface demo failures as test failures (ADR 043 v0.3).

A demo is an educational walkthrough, a live demonstration, AND a test. A broken
demo directly degrades the new-developer experience, so when the underlying
``demos/demo.py`` run fails, ``DemoTestRunner`` must report a failed result with
the failing output attached — never a silent pass. These tests lock that
contract without needing Docker (the subprocess is stubbed).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from hop3_testing.catalog.models import (
    DemoConfig,
    Priority,
    TestDefinition,
    TestRequirements,
    Tier,
)
from hop3_testing.runners import DemoTestRunner
from hop3_testing.targets.base import TargetInfo

if TYPE_CHECKING:
    from pathlib import Path


def _demo_tree(tmp_path: Path) -> TestDefinition:
    """Build a minimal demos/ tree so _resolve_demo_cli succeeds."""
    demos = tmp_path / "demos"
    (demos / "lib").mkdir(parents=True)
    (demos / "demo.py").write_text("# fake demo CLI\n")
    demo_dir = demos / "demoX"
    demo_dir.mkdir()
    (demo_dir / "demo-script.py").write_text("# demo\n")
    return TestDefinition(
        name="demos/demoX",
        tier=Tier.FAST,
        priority=Priority.P1,
        requirements=TestRequirements(),
        demo=DemoConfig(script="demo-script.py", type="script"),
        source_path=demo_dir / "test.toml",  # parent == demo_dir
    )


def _runner() -> DemoTestRunner:
    target = SimpleNamespace(info=TargetInfo(ssh_host="", ssh_port=22))
    return DemoTestRunner(cast("Any", target))


def test_failed_demo_is_reported_as_failed(tmp_path, monkeypatch):
    test = _demo_tree(tmp_path)

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout="Deploying demoX...\n",
            stderr="boom: deploy failed\n",
        )

    monkeypatch.setattr("hop3_testing.runners.demo.run_captured", fake_run)

    result = _runner().run(test)

    assert result.passed is False
    assert result.error is not None
    assert "exit code 1" in result.error
    # The failing output must be attached so an operator can see what broke.
    assert "boom: deploy failed" in result.error


def test_passing_demo_is_reported_as_passed(tmp_path, monkeypatch):
    test = _demo_tree(tmp_path)

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("hop3_testing.runners.demo.run_captured", fake_run)

    result = _runner().run(test)

    assert result.passed is True
    assert result.error is None


def test_demo_timeout_is_reported_as_failed(tmp_path, monkeypatch):
    import subprocess  # noqa: PLC0415

    test = _demo_tree(tmp_path)

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 600)

    monkeypatch.setattr("hop3_testing.runners.demo.run_captured", fake_run)

    result = _runner().run(test)

    assert result.passed is False
    assert result.error is not None
    assert "timed out" in result.error.lower()


def test_demo_timeout_captures_partial_output(tmp_path, monkeypatch):
    """A hung demo must still surface its partial output, not 'No logs recorded'.

    ``subprocess.run(capture_output=True, timeout=…)`` populates the
    TimeoutExpired's stdout/stderr with what was captured before the kill; the
    runner must persist that as the log (this is the dashboard's only window
    into why a 600s demo hung).
    """
    import subprocess  # noqa: PLC0415

    test = _demo_tree(tmp_path)

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd,
            600,
            output="Deploying demoX...\nStep 5: hung here\n",
            stderr="warn: slow\n",
        )

    monkeypatch.setattr("hop3_testing.runners.demo.run_captured", fake_run)

    result = _runner().run(test)

    assert result.passed is False
    assert "timed out" in result.error.lower()
    # Partial output captured before the kill must be persisted (was lost before).
    assert "Step 5: hung here" in result.deploy_logs
    assert "warn: slow" in result.deploy_logs
    # ...and a tail surfaced in the error message for quick triage.
    assert "Step 5: hung here" in result.error
