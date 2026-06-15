# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Failures-first run ordering + planned per-type counts (testlab features).

A re-run starts with the previous run's failures (same family = mode +
target_type) so regressions surface fast, and the run records how many tests of
each type (app/demo/tutorial) are planned so the live dashboard can show
progress.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from hop3_testing.cli.runners import _count_by_type, _order_failed_first
from hop3_testing.results import ResultStore
from hop3_testing.results.models import TestResultRecord

if TYPE_CHECKING:
    from pathlib import Path


class _Console:
    def status(self, *args, **kwargs) -> None:
        pass


def _finished_run(store, *, mode, target_type, results):
    """Create a FINISHED run of the given family with (name, passed) results."""
    run = store.start_run(mode=mode, target_type=target_type, target_name="t")
    session = store.Session()
    session.add_all(
        TestResultRecord(run_id=run.id, test_name=name, passed=passed)
        for name, passed in results
    )
    session.commit()
    session.close()
    store.finish_run()
    return run


def _tests(*names, runner_type="deployment"):
    return [SimpleNamespace(name=n, runner_type=runner_type) for n in names]


def test_previous_failures_picks_last_finished_run_of_family(tmp_path: Path):
    store = ResultStore(db_path=tmp_path / "r.db")
    _finished_run(
        store,
        mode="nightly",
        target_type="docker",
        results=[("apps/a", True), ("apps/b", False), ("apps/c", False)],
    )
    assert store.previous_failures(mode="nightly", target_type="docker") == {
        "apps/b",
        "apps/c",
    }
    # A different family shares nothing.
    assert store.previous_failures(mode="nightly", target_type="ssh") == set()
    assert store.previous_failures(mode="ci", target_type="docker") == set()


def test_previous_failures_ignores_unfinished_runs(tmp_path: Path):
    store = ResultStore(db_path=tmp_path / "r.db")
    run = store.start_run(mode="nightly", target_type="docker", target_name="t")
    session = store.Session()
    session.add(TestResultRecord(run_id=run.id, test_name="apps/x", passed=False))
    session.commit()
    session.close()
    # Not finished → not a basis for the next run's ordering.
    assert store.previous_failures(mode="nightly", target_type="docker") == set()


def test_order_failed_first(tmp_path: Path):
    store = ResultStore(db_path=tmp_path / "r.db")
    _finished_run(
        store,
        mode="nightly",
        target_type="docker",
        results=[("apps/a", True), ("apps/b", False)],
    )
    ordered = _order_failed_first(
        _tests("apps/a", "apps/b", "apps/c"),
        store,
        mode="nightly",
        target_type="docker",
        console=_Console(),
    )
    # The prior failure (apps/b) runs first; the rest stay in name order.
    assert [t.name for t in ordered] == ["apps/b", "apps/a", "apps/c"]


def test_order_failed_first_without_history_is_alphabetical(tmp_path: Path):
    store = ResultStore(db_path=tmp_path / "r.db")
    ordered = _order_failed_first(
        _tests("apps/c", "apps/a", "apps/b"),
        store,
        mode="nightly",
        target_type="docker",
        console=_Console(),
    )
    assert [t.name for t in ordered] == ["apps/a", "apps/b", "apps/c"]


def test_demos_kept_in_name_order_despite_failed_first(tmp_path: Path):
    """Demos are an ordered ladder: failed-first must not reorder them (else a
    later-failing demo would run before demo01 and break demo fail-fast). Demos
    stay in name order and come after the non-demos."""
    store = ResultStore(db_path=tmp_path / "r.db")
    _finished_run(
        store,
        mode="nightly",
        target_type="docker",
        results=[("demos/demo03", False), ("apps/b", False)],
    )
    tests = [
        *_tests("apps/a", "apps/b"),
        *_tests("demos/demo03", "demos/demo01", "demos/demo02", runner_type="demo"),
    ]
    ordered = _order_failed_first(
        tests, store, mode="nightly", target_type="docker", console=_Console()
    )
    names = [t.name for t in ordered]
    # apps/b failed → first among non-demos; demos stay name-ordered, at the end.
    assert names[0] == "apps/b"
    assert names[-3:] == ["demos/demo01", "demos/demo02", "demos/demo03"]


def test_count_by_type():
    tests = [
        *_tests("apps/x", "apps/y"),
        *_tests("demos/d", runner_type="demo"),
        *_tests("docs/t", runner_type="tutorial"),
    ]
    assert _count_by_type(tests) == {"app": 2, "demo": 1, "tutorial": 1}


def test_start_run_records_planned_counts(tmp_path: Path):
    store = ResultStore(db_path=tmp_path / "r.db")
    run = store.start_run(
        mode="nightly",
        target_type="docker",
        target_name="t",
        planned_counts={"app": 5, "demo": 2, "tutorial": 3},
    )
    assert run.planned_counts == {"app": 5, "demo": 2, "tutorial": 3}
