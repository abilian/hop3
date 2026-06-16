# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for mount startup reconciliation (mocked mount helper)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from hop3_rootd import reconcile as rec
from hop3_rootd.mount import MountError
from hop3_rootd.state import State, StoredMount


def _state(*mounts: StoredMount) -> State:
    return State(mounts=list(mounts))


def test_reconcile_keeps_live_drops_stale_removes_orphan():
    state = _state(
        StoredMount("blog", "a", "tmpfs", None, "t"),  # live
        StoredMount("blog", "b", "tmpfs", None, "t"),  # stale (not mounted)
    )
    with (
        patch.object(
            rec.mt,
            "mountpoint_for",
            side_effect=lambda app, target: Path(f"/app/{target}"),
        ),
        patch.object(rec.mt, "is_mounted", side_effect=lambda mp: str(mp) == "/app/a"),
        patch.object(
            rec.mt, "list_mounts_under_app_root", return_value=["/app/a", "/app/orphan"]
        ),
        patch.object(rec.mt, "unmount_path") as mock_un,
    ):
        report = rec.reconcile_mounts(state)

    assert report.verified == 1
    assert report.state_dropped == 1
    assert report.orphans_removed == 1
    assert [m.target for m in state.mounts] == ["a"]  # stale dropped, live kept
    mock_un.assert_called_once_with(Path("/app/orphan"))  # live mount NOT touched


def test_reconcile_mounts_app_root_underivable_propagates():
    state = _state(StoredMount("blog", "a", "tmpfs", None, "t"))
    with (
        patch.object(rec.mt, "mountpoint_for", side_effect=MountError("no app root")),
        pytest.raises(MountError),
    ):
        rec.reconcile_mounts(state)


def test_reconcile_orphan_unmount_failure_is_counted_not_fatal():
    state = _state()  # nothing tracked → only orphan scan runs
    with (
        patch.object(
            rec.mt, "list_mounts_under_app_root", return_value=["/app/orphan"]
        ),
        patch.object(rec.mt, "unmount_path", side_effect=MountError("busy")),
    ):
        report = rec.reconcile_mounts(state)
    assert report.orphans_removed == 0  # failed, logged, did not crash
    assert report.verified == 0
