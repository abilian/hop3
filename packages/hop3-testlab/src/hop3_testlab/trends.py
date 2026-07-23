# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Run-to-run comparison (the morning regressions diff).

Pure functions over result records, so they're unit-testable without a DB.
"""

from __future__ import annotations

from itertools import pairwise
from statistics import median
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from collections.abc import Iterable

    from hop3_testing.results.models import TestResultRecord


class RunDiff(TypedDict):
    regressions: list[str]
    fixed: list[str]
    still_failing: list[str]
    not_run: list[str]


class RunProgress(TypedDict):
    elapsed_seconds: float
    done: int
    expected_total: int | None
    progress_pct: int | None
    typical_seconds: float | None
    eta_seconds: float | None


# Enough completed tests before we trust the live count-rate over history.
_MIN_DONE_FOR_RATE = 3


def predict_progress(
    *,
    started_epoch: float,
    now_epoch: float,
    done: int,
    history_durations: list[float],
    history_totals: list[int],
) -> RunProgress:
    """
    Estimate a running suite's progress + ETA from history (pure, DB-free).

    ``done`` is the number of tests finished so far (the running run's growing
    ``total_tests``). History is the durations/test-counts of recent *completed*
    comparable runs (same mode+target). We prefer the live count-rate once a few
    tests are in (it adapts to today's machine/load) and fall back to the typical
    historical duration early on; either may be missing, hence the Nones.
    """
    elapsed = max(now_epoch - started_epoch, 0.0)
    typical = median(history_durations) if history_durations else None
    expected_total = round(median(history_totals)) if history_totals else None

    # Progress %: prefer the count ratio; else time-vs-typical; else indeterminate.
    progress_pct: int | None = None
    if expected_total and expected_total > 0:
        progress_pct = min(99, round(100 * done / expected_total))
    elif typical and typical > 0:
        progress_pct = min(99, round(100 * elapsed / typical))

    # ETA: count-rate extrapolation once enough tests are in, else history.
    eta_count: float | None = None
    if done >= 1 and expected_total and expected_total > done:
        eta_count = (elapsed / done) * (expected_total - done)
    eta_typical: float | None = None
    if typical is not None:
        eta_typical = max(typical - elapsed, 0.0)

    eta_seconds: float | None
    if done >= _MIN_DONE_FOR_RATE and eta_count is not None:
        eta_seconds = eta_count
    elif eta_typical is not None:
        eta_seconds = eta_typical
    else:
        eta_seconds = eta_count

    return RunProgress(
        elapsed_seconds=elapsed,
        done=done,
        expected_total=expected_total,
        progress_pct=progress_pct,
        typical_seconds=typical,
        eta_seconds=eta_seconds,
    )


def _is_true_failure(r: TestResultRecord) -> bool:
    """
    A real failure — not xfail/xpass (negative tests). Falls back to ``passed``
    for legacy rows / stubs without a status.
    """
    status = getattr(r, "status", None)
    if status:
        return status == "fail"
    return not r.passed


def diff_results(
    current: Iterable[TestResultRecord],
    previous: Iterable[TestResultRecord],
) -> RunDiff:
    """
    Compare two runs, considering ONLY tests run in both (xfail/xpass excluded).

    A test that failed before but wasn't re-run is NOT "fixed" — it's ``not_run``.
    Comparing only the intersection keeps regressions/fixed/still-failing accurate
    when the runs cover different sets (e.g. a 6-test manual run vs a 199-test
    nightly).

    - ``regressions``  — failing now, passing before (the actionable set)
    - ``fixed``        — passing now, failing before (genuinely re-run + green)
    - ``still_failing``— failing in both
    - ``not_run``      — present in the previous run but not re-run here
    """
    now = {r.test_name: _is_true_failure(r) for r in current}
    prev = {r.test_name: _is_true_failure(r) for r in previous}
    common = now.keys() & prev.keys()
    return RunDiff(
        regressions=sorted(n for n in common if now[n] and not prev[n]),
        fixed=sorted(n for n in common if prev[n] and not now[n]),
        still_failing=sorted(n for n in common if now[n] and prev[n]),
        not_run=sorted(prev.keys() - now.keys()),
    )


def suite_rollup(
    results: Iterable[TestResultRecord],
) -> dict[str, dict[str, int]]:
    """
    Group results by category -> counts. Only true failures count as failed;
    xfail/xpass land in ``passed`` (the run isn't red for them).
    """
    rollup: dict[str, dict[str, int]] = {}
    for r in results:
        bucket = rollup.setdefault(
            r.category or "other", {"total": 0, "passed": 0, "failed": 0}
        )
        bucket["total"] += 1
        bucket["failed" if _is_true_failure(r) else "passed"] += 1
    return dict(sorted(rollup.items()))


def flakiness_ranking(history: dict[str, list[bool]]) -> list[tuple[str, int]]:
    """
    Rank tests by how often they flip pass<->fail across runs (most first).

    ``history`` maps a test name to its pass/fail outcomes in run order
    (oldest first). Tests that never flipped are omitted.
    """
    ranked = [
        (name, flips)
        for name, seq in history.items()
        if (flips := sum(a != b for a, b in pairwise(seq)))
    ]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked
