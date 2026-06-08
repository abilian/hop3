# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Tests for the --narrate timing reporter (ADR 043 phase 3)."""

from __future__ import annotations

import io

from hop3_testing.catalog.models import (
    Priority,
    TestDefinition,
    TestRequirements,
    Tier,
)
from hop3_testing.results.reporters import narrate_timings
from hop3_testing.runners.base import TestResult, ValidationResult
from hop3_testing.util.timing import format_duration


def _td(name: str) -> TestDefinition:
    return TestDefinition(
        name=name,
        tier=Tier.FAST,
        priority=Priority.P1,
        requirements=TestRequirements(),
    )


def _result(name: str, total: float, phases: list[tuple[str, float]]) -> TestResult:
    vrs = [
        ValidationResult(passed=True, message="", duration=d, validation_type=t)
        for t, d in phases
    ]
    return TestResult(
        test=_td(name),
        passed=True,
        validation_results=vrs,
        total_duration=total,
    )


def test_format_duration_seconds():
    assert format_duration(1.5) == "1.5s"
    assert format_duration(59.9) == "59.9s"


def test_format_duration_minutes():
    assert format_duration(60) == "1m 0.0s"
    assert format_duration(95.0) == "1m 35.0s"


def test_narrate_empty_is_silent():
    out = io.StringIO()
    narrate_timings([], output=out)
    assert out.getvalue() == ""


def test_narrate_orders_slowest_first_with_phases_and_totals():
    out = io.StringIO()
    results = [
        _result("fast-app", 10.0, [("deploy", 8.0), ("http", 2.0)]),
        _result("slow-app", 100.0, [("deploy", 90.0), ("http", 10.0)]),
    ]
    narrate_timings(results, output=out)
    text = out.getvalue()

    # Slowest first.
    assert text.index("slow-app") < text.index("fast-app")
    # Per-phase breakdown rendered with format_duration.
    assert "deploy 1m 30.0s" in text  # slow-app deploy 90s
    assert "http 2.0s" in text
    # Footer totals: wall=110s, deploy=98s, slowest named.
    assert "total wall 1m 50.0s" in text
    assert "deploy 1m 38.0s" in text
    assert "slowest slow-app" in text
