# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for mount ops (mocked mount helper)."""

from __future__ import annotations

from unittest.mock import ANY, patch

import pytest
from hop3_rootd import PROTOCOL_VERSION, mount
from hop3_rootd.mount import MountError
from hop3_rootd.ops import get_handler
from hop3_rootd.ops._base import OpContext
from hop3_rootd.protocol import Request
from hop3_rootd.state import State, StoredMount
from hop3_rootd.validation import ValidationError

from tests.a_unit._fakes import SaveSpy


@pytest.fixture
def save_spy() -> SaveSpy:
    return SaveSpy()


@pytest.fixture
def ctx(save_spy: SaveSpy) -> OpContext:
    return OpContext(
        state=State(),
        state_path=None,
        save_state=save_spy,
        now_iso=lambda: "2026-04-24T15:30:00+00:00",
        new_rule_id=lambda: "rule-test-1",
    )


def _req(op: str, **args) -> Request:
    return Request(v=PROTOCOL_VERSION, id="req-1", op=op, args=args)


# --- mount.tmpfs ---------------------------------------------------------


def test_tmpfs_happy_path_records_state(ctx, save_spy):
    handler = get_handler("mount.tmpfs")
    assert handler is not None
    with patch.object(
        mount,
        "mount_tmpfs",
        return_value={
            "mountpoint": "/home/hop3/apps/blog/src/var/cache",
            "type": "tmpfs",
        },
    ) as mock_mt:
        result = handler(
            _req(
                "mount.tmpfs", app_name="blog", target="var/cache", size_bytes=1048576
            ),
            ctx,
        )
    mock_mt.assert_called_once_with("blog", "var/cache", 1048576, None, exec=ANY)
    assert result["mountpoint"].endswith("var/cache")
    assert len(ctx.state.mounts) == 1
    assert ctx.state.mounts[0].type == "tmpfs"
    assert ctx.state.mounts[0].target == "var/cache"
    assert save_spy.count == 1


def test_tmpfs_rejects_absolute_target(ctx):
    handler = get_handler("mount.tmpfs")
    assert handler is not None
    with (
        patch.object(mount, "mount_tmpfs") as mock_mt,
        pytest.raises(ValidationError),
    ):
        handler(
            _req("mount.tmpfs", app_name="blog", target="/etc/x", size_bytes=1048576),
            ctx,
        )
    mock_mt.assert_not_called()
    assert ctx.state.mounts == []


def test_tmpfs_rejects_missing_size(ctx):
    handler = get_handler("mount.tmpfs")
    assert handler is not None
    with (
        patch.object(mount, "mount_tmpfs") as mock_mt,
        pytest.raises(ValidationError),
    ):
        handler(_req("mount.tmpfs", app_name="blog", target="var/cache"), ctx)
    mock_mt.assert_not_called()


def test_tmpfs_replaces_existing_same_target(ctx):
    ctx.state.mounts.append(
        StoredMount("blog", "var/cache", "tmpfs", None, "2026-01-01T00:00:00+00:00")
    )
    handler = get_handler("mount.tmpfs")
    assert handler is not None
    with patch.object(
        mount, "mount_tmpfs", return_value={"mountpoint": "/x", "type": "tmpfs"}
    ):
        handler(
            _req("mount.tmpfs", app_name="blog", target="var/cache", size_bytes=2048),
            ctx,
        )
    assert len(ctx.state.mounts) == 1


# --- mount.bind ----------------------------------------------------------


def test_bind_happy_path_records_state(ctx, save_spy):
    handler = get_handler("mount.bind")
    assert handler is not None
    with patch.object(
        mount,
        "mount_bind",
        return_value={
            "mountpoint": "/home/hop3/apps/blog/src/public/media",
            "type": "bind",
            "source": "/srv/shared/media",
            "read_only": False,
        },
    ) as mock_mb:
        result = handler(
            _req(
                "mount.bind",
                app_name="blog",
                target="public/media",
                source="/srv/shared/media",
            ),
            ctx,
        )
    mock_mb.assert_called_once_with(
        "blog", "public/media", "/srv/shared/media", read_only=False, exec=ANY
    )
    assert result["type"] == "bind"
    assert ctx.state.mounts[0].type == "bind"
    assert ctx.state.mounts[0].source == "/srv/shared/media"
    assert save_spy.count == 1


def test_bind_rejects_relative_source(ctx):
    handler = get_handler("mount.bind")
    assert handler is not None
    with (
        patch.object(mount, "mount_bind") as mock_mb,
        pytest.raises(ValidationError),
    ):
        handler(
            _req("mount.bind", app_name="blog", target="public/media", source="srv/x"),
            ctx,
        )
    mock_mb.assert_not_called()
    assert ctx.state.mounts == []


def test_bind_denied_source_propagates(ctx):
    """A denied bind source aborts loudly (dispatcher → kernel_error)."""
    handler = get_handler("mount.bind")
    assert handler is not None
    with (
        patch.object(
            mount,
            "mount_bind",
            side_effect=MountError("not under any operator-allowed"),
        ),
        pytest.raises(MountError),
    ):
        handler(
            _req(
                "mount.bind",
                app_name="blog",
                target="public/media",
                source="/etc/secret",
            ),
            ctx,
        )
    assert ctx.state.mounts == []


# --- mount.unmount -------------------------------------------------------


def test_unmount_drops_state(ctx, save_spy):
    ctx.state.mounts.append(
        StoredMount("blog", "var/cache", "tmpfs", None, "2026-01-01T00:00:00+00:00")
    )
    handler = get_handler("mount.unmount")
    assert handler is not None
    with patch.object(
        mount,
        "unmount",
        return_value={"unmounted": True, "mountpoint": "/x", "method": "umount"},
    ):
        result = handler(
            _req("mount.unmount", app_name="blog", target="var/cache"), ctx
        )
    assert result["unmounted"] is True
    assert ctx.state.mounts == []
    assert save_spy.count == 1


def test_unmount_only_drops_matching_target(ctx):
    ctx.state.mounts.extend([
        StoredMount("blog", "var/cache", "tmpfs", None, "t"),
        StoredMount("blog", "data/up", "tmpfs", None, "t"),
    ])
    handler = get_handler("mount.unmount")
    assert handler is not None
    with patch.object(
        mount,
        "unmount",
        return_value={"unmounted": True, "mountpoint": "/x", "method": "umount"},
    ):
        handler(_req("mount.unmount", app_name="blog", target="var/cache"), ctx)
    assert [m.target for m in ctx.state.mounts] == ["data/up"]


# --- mount.list ----------------------------------------------------------


def test_list_returns_all_and_filters(ctx):
    ctx.state.mounts.extend([
        StoredMount("blog", "var/cache", "tmpfs", None, "t"),
        StoredMount("wiki", "data/up", "tmpfs", None, "t"),
    ])
    handler = get_handler("mount.list")
    assert handler is not None

    all_result = handler(_req("mount.list"), ctx)
    assert len(all_result["mounts"]) == 2

    filtered = handler(_req("mount.list", app_name="blog"), ctx)
    assert len(filtered["mounts"]) == 1
    assert filtered["mounts"][0]["app_name"] == "blog"


def test_list_validates_app_filter(ctx):
    handler = get_handler("mount.list")
    assert handler is not None
    with pytest.raises(ValidationError):
        handler(_req("mount.list", app_name="bad name!"), ctx)
