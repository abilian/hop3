# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The text report's target-diagnostics block."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from hop3_testing.cli.reports import generate_reports
from hop3_testing.diagnostics import DiagnosticCollector
from hop3_testing.runners.base import TestResult

if TYPE_CHECKING:
    from pathlib import Path


class _Target:
    def __init__(self, diagnostics: DiagnosticCollector, tmp_path: Path) -> None:
        self.diagnostics = diagnostics
        self._tmp_path = tmp_path

    def save_diagnostics(self, *, generate_html: bool) -> Path:
        return self._tmp_path


def _failed_test() -> TestResult:
    return TestResult(test=cast("Any", None), passed=False, error="hash mismatch")


def test_a_target_without_failures_prints_no_block_under_failed_tests(
    tmp_path: Path, capsys
) -> None:
    # The block said "No failures recorded." beneath "1 of 1 tests failed".
    target = _Target(DiagnosticCollector(), tmp_path)
    generate_reports(cast("Any", target), "text", [_failed_test()])
    out = capsys.readouterr().out
    assert "Diagnostic logs saved to" in out
    assert "No failures recorded" not in out


def test_a_target_failure_is_printed(tmp_path: Path, capsys) -> None:
    diagnostics = DiagnosticCollector()
    diagnostics.add_failure("docker", "start_container", "port 8443 is taken")
    target = _Target(diagnostics, tmp_path)
    generate_reports(cast("Any", target), "text", [_failed_test()])
    assert "port 8443 is taken" in capsys.readouterr().out
