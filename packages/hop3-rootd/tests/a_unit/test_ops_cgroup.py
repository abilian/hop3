# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for cgroup ops (mocked cgroup fs helper).

The ops layer is tested against a patched ``hop3_rootd.cgroup`` so these
tests verify the contract (validation, state updates, return shape, error
propagation) without touching ``/sys/fs/cgroup``. The fs helper itself is
tested in test_cgroup.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_rootd import PROTOCOL_VERSION, cgroup
from hop3_rootd.cgroup import CgroupUnavailableError
from hop3_rootd.ops import get_handler
from hop3_rootd.ops._base import OpContext
from hop3_rootd.protocol import Request
from hop3_rootd.state import State, StoredCgroup
from hop3_rootd.validation import ValidationError

from tests.a_unit._fakes import SaveSpy

# --- Fixtures -------------------------------------------------------------


@pytest.fixture
def save_spy() -> SaveSpy:
    return SaveSpy()


@pytest.fixture
def ctx(save_spy: SaveSpy) -> OpContext:
    return OpContext(
        state=State(),
        save_state=save_spy,
        now_iso=lambda: "2026-04-24T15:30:00+00:00",
        new_rule_id=lambda: "rule-test-1",
    )


def _req(op: str, **args) -> Request:
    return Request(v=PROTOCOL_VERSION, id="req-1", op=op, args=args)


# --- cgroup.ensure_slice -------------------------------------------------


def test_ensure_slice_returns_helper_result(ctx):
    handler = get_handler("cgroup.ensure_slice")
    assert handler is not None
    with patch.object(
        cgroup,
        "ensure_slice",
        return_value={
            "slice_path": "/sys/fs/cgroup/hop3.slice",
            "controllers": ["cpu", "memory", "pids"],
        },
    ):
        result = handler(_req("cgroup.ensure_slice"), ctx)
    assert result["slice_path"].endswith("hop3.slice")
    assert "memory" in result["controllers"]


def test_ensure_slice_unavailable_propagates(ctx):
    """A host that can't enforce limits raises (dispatcher → kernel_error)."""
    handler = get_handler("cgroup.ensure_slice")
    assert handler is not None
    with (
        patch.object(
            cgroup, "ensure_slice", side_effect=CgroupUnavailableError("no v2")
        ),
        pytest.raises(CgroupUnavailableError),
    ):
        handler(_req("cgroup.ensure_slice"), ctx)


# --- cgroup.set_limits ---------------------------------------------------


def test_set_limits_happy_path(ctx, save_spy):
    handler = get_handler("cgroup.set_limits")
    assert handler is not None
    with patch.object(
        cgroup,
        "set_limits",
        return_value={
            "cgroup_path": "/sys/fs/cgroup/hop3.slice/hop3-app-blog.scope",
            "applied": {"memory_max": 536870912, "cpu_max": "150000 100000"},
        },
    ) as mock_set:
        result = handler(
            _req(
                "cgroup.set_limits",
                app_name="blog",
                memory_max=536870912,
                cpu_max="150000 100000",
            ),
            ctx,
        )

    mock_set.assert_called_once_with(
        "blog", memory_max=536870912, cpu_max="150000 100000", pids_max=None
    )
    assert result["app_name"] == "blog"
    assert result["applied"]["memory_max"] == 536870912
    assert result["applied_at"] == "2026-04-24T15:30:00+00:00"
    # State records the cap; save was called.
    assert len(ctx.state.cgroups) == 1
    assert ctx.state.cgroups[0].app_name == "blog"
    assert ctx.state.cgroups[0].memory_max == 536870912
    assert save_spy.count == 1


def test_set_limits_no_dimension_is_validation_error(ctx):
    """A set_limits with no cap would create a looks-enforced-but-empty leaf."""
    handler = get_handler("cgroup.set_limits")
    assert handler is not None
    with (
        patch.object(cgroup, "set_limits") as mock_set,
        pytest.raises(ValidationError),
    ):
        handler(_req("cgroup.set_limits", app_name="blog"), ctx)
    mock_set.assert_not_called()
    assert ctx.state.cgroups == []


def test_set_limits_bad_cpu_max_rejected(ctx):
    handler = get_handler("cgroup.set_limits")
    assert handler is not None
    with (
        patch.object(cgroup, "set_limits") as mock_set,
        pytest.raises(ValidationError),
    ):
        handler(_req("cgroup.set_limits", app_name="blog", cpu_max="1.5"), ctx)
    mock_set.assert_not_called()


def test_set_limits_replaces_existing_cap(ctx):
    """Refreshing caps for an app must not duplicate its state row."""
    ctx.state.cgroups.append(
        StoredCgroup("blog", 100, None, None, "2026-01-01T00:00:00+00:00")
    )
    handler = get_handler("cgroup.set_limits")
    assert handler is not None
    with patch.object(
        cgroup,
        "set_limits",
        return_value={"cgroup_path": "/x", "applied": {"memory_max": 999}},
    ):
        handler(_req("cgroup.set_limits", app_name="blog", memory_max=999), ctx)
    assert len(ctx.state.cgroups) == 1
    assert ctx.state.cgroups[0].memory_max == 999


# --- cgroup.attach_pids --------------------------------------------------


def test_attach_pids_happy_path(ctx):
    handler = get_handler("cgroup.attach_pids")
    assert handler is not None
    with patch.object(
        cgroup, "attach_pids", return_value={"attached": [10, 11], "failed": []}
    ) as mock_attach:
        result = handler(
            _req("cgroup.attach_pids", app_name="blog", pids=[10, 11]), ctx
        )
    mock_attach.assert_called_once_with("blog", [10, 11])
    assert result["attached"] == [10, 11]
    assert result["failed"] == []


def test_attach_pids_surfaces_failures(ctx):
    """A failed attach is reported, not swallowed — strict mode acts on it."""
    handler = get_handler("cgroup.attach_pids")
    assert handler is not None
    with patch.object(
        cgroup, "attach_pids", return_value={"attached": [10], "failed": [11]}
    ):
        result = handler(
            _req("cgroup.attach_pids", app_name="blog", pids=[10, 11]), ctx
        )
    assert result["failed"] == [11]


def test_attach_pids_empty_list_rejected(ctx):
    handler = get_handler("cgroup.attach_pids")
    assert handler is not None
    with (
        patch.object(cgroup, "attach_pids") as mock_attach,
        pytest.raises(ValidationError),
    ):
        handler(_req("cgroup.attach_pids", app_name="blog", pids=[]), ctx)
    mock_attach.assert_not_called()


# --- cgroup.remove -------------------------------------------------------


def test_remove_drops_state_and_reports(ctx, save_spy):
    ctx.state.cgroups.append(
        StoredCgroup("blog", 100, None, None, "2026-01-01T00:00:00+00:00")
    )
    handler = get_handler("cgroup.remove")
    assert handler is not None
    with patch.object(
        cgroup, "remove", return_value={"removed": True, "killed_pids": [42]}
    ):
        result = handler(_req("cgroup.remove", app_name="blog"), ctx)
    assert result["removed"] is True
    assert result["killed_pids"] == [42]
    assert ctx.state.cgroups == []
    assert save_spy.count == 1


def test_remove_absent_leaf_is_idempotent(ctx):
    handler = get_handler("cgroup.remove")
    assert handler is not None
    with patch.object(
        cgroup,
        "remove",
        return_value={"removed": False, "killed_pids": [], "kernel_state": "absent"},
    ):
        result = handler(_req("cgroup.remove", app_name="ghost"), ctx)
    assert result["removed"] is False
    assert result["kernel_state"] == "absent"


# --- cgroup.read ---------------------------------------------------------


def test_read_returns_helper_result(ctx):
    handler = get_handler("cgroup.read")
    assert handler is not None
    with patch.object(
        cgroup,
        "read",
        return_value={
            "memory_max": "536870912",
            "memory_current": "12345",
            "cpu_max": "150000 100000",
            "pids_max": "256",
            "pids_current": "7",
            "oom_kill": 2,
        },
    ):
        result = handler(_req("cgroup.read", app_name="blog"), ctx)
    assert result["app_name"] == "blog"
    assert result["oom_kill"] == 2


def test_read_bad_app_name_rejected(ctx):
    handler = get_handler("cgroup.read")
    assert handler is not None
    with pytest.raises(ValidationError):
        handler(_req("cgroup.read", app_name="bad name!"), ctx)
