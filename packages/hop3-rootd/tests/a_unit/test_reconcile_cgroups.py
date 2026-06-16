# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for cgroup startup reconciliation (mocked cgroup fs helper)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_rootd import reconcile as rec
from hop3_rootd.cgroup import CgroupError, CgroupUnavailableError
from hop3_rootd.state import State, StoredCgroup


def _state(*cgroups: StoredCgroup) -> State:
    return State(cgroups=list(cgroups))


def test_reconcile_reasserts_stored_and_removes_orphans():
    state = _state(StoredCgroup("blog", 536870912, "150000 100000", None, "t"))
    with (
        patch.object(rec.cg, "ensure_slice") as mock_ensure,
        patch.object(rec.cg, "set_limits") as mock_set,
        patch.object(rec.cg, "list_scopes", return_value=["blog", "ghost"]),
        patch.object(rec.cg, "remove") as mock_remove,
    ):
        report = rec.reconcile_cgroups(state)

    mock_ensure.assert_called_once()
    mock_set.assert_called_once_with(
        "blog", memory_max=536870912, cpu_max="150000 100000", pids_max=None
    )
    # "ghost" is on disk but not in state → removed as an orphan.
    mock_remove.assert_called_once_with("ghost")
    assert report.reasserted == 1
    assert report.orphans_removed == 1
    assert report.failed == 0


def test_reconcile_unavailable_host_propagates():
    """A non-v2 host raises so the caller degrades loudly, not silently."""
    with (
        patch.object(
            rec.cg, "ensure_slice", side_effect=CgroupUnavailableError("no v2")
        ),
        pytest.raises(CgroupUnavailableError),
    ):
        rec.reconcile_cgroups(_state(StoredCgroup("blog", 1, None, None, "t")))


def test_reconcile_counts_per_leaf_failure_without_crashing():
    state = _state(StoredCgroup("blog", 100, None, None, "t"))
    with (
        patch.object(rec.cg, "ensure_slice"),
        patch.object(rec.cg, "set_limits", side_effect=CgroupError("boom")),
        patch.object(rec.cg, "list_scopes", return_value=[]),
    ):
        report = rec.reconcile_cgroups(state)
    assert report.failed == 1
    assert report.reasserted == 0


def test_reconcile_no_state_no_orphans_is_noop():
    with (
        patch.object(rec.cg, "ensure_slice"),
        patch.object(rec.cg, "set_limits") as mock_set,
        patch.object(rec.cg, "list_scopes", return_value=[]),
        patch.object(rec.cg, "remove") as mock_remove,
    ):
        report = rec.reconcile_cgroups(_state())
    mock_set.assert_not_called()
    mock_remove.assert_not_called()
    assert report == rec.CgroupReconcileReport(
        reasserted=0, orphans_removed=0, failed=0
    )
