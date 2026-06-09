# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The meta runner must surface tutorial (validoc) failures (ADR 043 phase 3).

Tutorials verify that the docs match reality; a validoc failure means the
documented steps no longer work, which must be reported as a failed test, never
a silent pass. These tests lock TutorialTestRunner's contract without invoking
the real validoc (its result is stubbed).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from hop3_testing.catalog.models import (
    Priority,
    TestDefinition,
    TestRequirements,
    Tier,
    TutorialConfig,
)
from hop3_testing.runners import TutorialTestRunner
from hop3_testing.targets.base import TargetInfo

if TYPE_CHECKING:
    from pathlib import Path


def _tutorial(tmp_path: Path) -> TestDefinition:
    md = tmp_path / "flask.md"
    md.write_text("# Deploy Flask\n\nSteps...\n")
    return TestDefinition(
        name="python/flask",
        tier=Tier.SLOW,
        priority=Priority.P1,
        requirements=TestRequirements(),
        tutorial=TutorialConfig(path="flask.md", runner="validoc"),
        source_path=md,  # parent / tutorial.path == md
    )


def _runner() -> TutorialTestRunner:
    target = SimpleNamespace(info=TargetInfo(ssh_host="", ssh_port=22))
    return TutorialTestRunner(cast("Any", target))


def test_failed_validoc_is_reported_as_failed(tmp_path, monkeypatch):
    test = _tutorial(tmp_path)
    monkeypatch.setattr(
        TutorialTestRunner,
        "_run_validoc",
        lambda self, path, cwd: {
            "success": False,
            "error": "validoc failed with exit code 1",
            "logs": "block 3 failed",
        },
    )

    result = _runner().run(test)

    assert result.passed is False
    assert result.error is not None
    assert "validoc failed" in result.error


def test_passing_validoc_is_reported_as_passed(tmp_path, monkeypatch):
    test = _tutorial(tmp_path)
    monkeypatch.setattr(
        TutorialTestRunner,
        "_run_validoc",
        lambda self, path, cwd: {"success": True, "logs": "all blocks passed"},
    )

    result = _runner().run(test)

    assert result.passed is True
    assert result.error is None


def test_missing_tutorial_file_is_reported_as_failed(tmp_path):
    # source_path points at a file that does not exist -> hard failure, not a pass.
    test = TestDefinition(
        name="python/ghost",
        tier=Tier.SLOW,
        priority=Priority.P1,
        requirements=TestRequirements(),
        tutorial=TutorialConfig(path="ghost.md", runner="validoc"),
        source_path=tmp_path / "ghost.md",
    )

    result = _runner().run(test)

    assert result.passed is False
    assert result.error is not None
    assert "not found" in result.error.lower()
