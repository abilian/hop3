# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Run-to-run diff (the morning regressions view) — pure logic, no DB."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from hop3_testlab.trends import (
    diff_results,
    flakiness_ranking,
    predict_progress,
    suite_rollup,
)


def test_predict_progress_uses_count_rate_once_enough_done():
    # 6 of ~12 done in 60s -> ~60s remaining; expected_total = median([12, 12]).
    prog = predict_progress(
        started_epoch=1000.0,
        now_epoch=1060.0,
        done=6,
        history_durations=[100.0, 140.0],
        history_totals=[12, 12],
    )
    assert prog["expected_total"] == 12
    assert prog["progress_pct"] == 50
    assert prog["eta_seconds"] == 60.0  # (60/6) * (12-6)
    assert prog["elapsed_seconds"] == 60.0


def test_predict_progress_falls_back_to_history_early():
    # 0 done -> can't extrapolate; use typical duration minus elapsed.
    prog = predict_progress(
        started_epoch=1000.0,
        now_epoch=1030.0,
        done=0,
        history_durations=[120.0, 120.0],
        history_totals=[10, 10],
    )
    assert prog["typical_seconds"] == 120.0
    assert prog["eta_seconds"] == 90.0  # 120 - 30


def test_predict_progress_no_history_is_indeterminate():
    prog = predict_progress(
        started_epoch=1000.0,
        now_epoch=1010.0,
        done=2,
        history_durations=[],
        history_totals=[],
    )
    assert prog["expected_total"] is None
    assert prog["progress_pct"] is None
    assert prog["eta_seconds"] is None


def test_predict_progress_caps_percent_when_overrunning():
    # More done than history suggests -> bar pinned at 99 (not finished yet).
    prog = predict_progress(
        started_epoch=1000.0,
        now_epoch=1100.0,
        done=20,
        history_durations=[50.0],
        history_totals=[10],
    )
    assert prog["progress_pct"] == 99
    assert prog["eta_seconds"] == 0.0  # typical already exceeded


def _r(name: str, passed: bool):
    return SimpleNamespace(test_name=name, passed=passed)


def test_suite_rollup_groups_by_category():
    results = [
        SimpleNamespace(category="deployment", passed=True),
        SimpleNamespace(category="deployment", passed=False),
        SimpleNamespace(category="demo", passed=True),
        SimpleNamespace(category=None, passed=True),
    ]
    rollup = suite_rollup(cast("Any", results))
    assert rollup["deployment"] == {"total": 2, "passed": 1, "failed": 1}
    assert rollup["demo"] == {"total": 1, "passed": 1, "failed": 0}
    assert rollup["other"] == {"total": 1, "passed": 1, "failed": 0}


def test_flakiness_ranks_by_flips_and_drops_steady():
    history = {
        "steady": [True, True, True],
        "flaky": [True, False, True, False],  # 3 flips
        "one-flip": [True, False],  # 1 flip
    }
    assert flakiness_ranking(history) == [("flaky", 3), ("one-flip", 1)]


def test_diff_classifies_regressions_fixed_still_failing():
    previous = [_r("a", True), _r("b", False), _r("c", False)]
    current = [_r("a", False), _r("b", True), _r("c", False)]

    diff = diff_results(current, previous)

    assert diff["regressions"] == ["a"]  # passing before -> failing now
    assert diff["fixed"] == ["b"]  # failing before -> passing now
    assert diff["still_failing"] == ["c"]


def test_diff_with_no_previous_run_is_empty():
    # Nothing to compare against -> no regressions/fixed (the failures still show
    # in the results table; they're just not a *diff*).
    current = [_r("x", False), _r("y", True), _r("z", False)]

    diff = diff_results(current, [])

    assert diff["regressions"] == []
    assert diff["fixed"] == []
    assert diff["still_failing"] == []
    assert diff["not_run"] == []


def test_diff_not_rerun_tests_are_not_fixed():
    # The bug: a small run vs a big previous run must NOT report the un-run
    # previous failures as "fixed" — they're "not_run".
    previous = [_r("a", False), _r("b", False), _r("kept", False)]  # all failed
    current = [_r("kept", True)]  # only "kept" re-run, now passes

    diff = diff_results(current, previous)

    assert diff["fixed"] == ["kept"]  # genuinely re-run + green
    assert diff["not_run"] == ["a", "b"]  # not re-run -> NOT fixed
    assert diff["regressions"] == []


def _rs(name: str, status: str):
    # status-bearing record (the store sets these); passed is incidental here.
    return SimpleNamespace(test_name=name, status=status, passed=status != "fail")


def test_diff_excludes_xfail_and_xpass():
    # Only a true "fail" is a regression — xfail/xpass (bad recipes) are not.
    previous = [_rs("real", "pass"), _rs("bad", "pass"), _rs("surprise", "pass")]
    current = [_rs("real", "fail"), _rs("bad", "xfail"), _rs("surprise", "xpass")]

    diff = diff_results(current, previous)

    assert diff["regressions"] == ["real"]  # xfail/xpass are not regressions
    assert diff["fixed"] == []
