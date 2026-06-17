# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for proxy ops (mocked proxy helper)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_rootd import PROTOCOL_VERSION, proxy
from hop3_rootd.ops import get_handler
from hop3_rootd.ops._base import OpContext
from hop3_rootd.protocol import Request
from hop3_rootd.state import State, StoredProxy
from hop3_rootd.validation import ValidationError


@pytest.fixture
def ctx():
    state = State()
    saved = {"count": 0}

    def save_state():
        saved["count"] += 1

    context = OpContext(
        state=state,
        state_path=None,
        save_state=save_state,
        now_iso=lambda: "2026-06-16T10:00:00+00:00",
        new_rule_id=lambda: "rule-1",
    )
    context._saved = saved  # type: ignore[attr-defined]
    return context


def _req(op: str, **args) -> Request:
    return Request(v=PROTOCOL_VERSION, id="req-1", op=op, args=args)


# --- proxy.add -----------------------------------------------------------


def test_add_records_state(ctx):
    handler = get_handler("proxy.add")
    assert handler is not None
    with patch.object(
        proxy,
        "add_proxy",
        return_value={
            "unit": "hop3-expose-postgres-mydb",
            "public_port": 54312,
            "target_port": 5432,
        },
    ) as mock_add:
        result = handler(
            _req(
                "proxy.add",
                addon_type="postgres",
                addon_name="mydb",
                public_port=54312,
                target_port=5432,
                source="203.0.113.0/24",
            ),
            ctx,
        )

    mock_add.assert_called_once_with("postgres", "mydb", 54312, 5432)
    assert result["unit"] == "hop3-expose-postgres-mydb"
    assert result["source"] == "203.0.113.0/24"
    assert len(ctx.state.proxies) == 1
    sp = ctx.state.proxies[0]
    assert (sp.addon_type, sp.addon_name, sp.public_port, sp.target_port) == (
        "postgres",
        "mydb",
        54312,
        5432,
    )
    assert ctx._saved["count"] == 1


def test_add_replaces_existing_for_same_addon(ctx):
    ctx.state.proxies.append(
        StoredProxy(
            "postgres", "mydb", "hop3-expose-postgres-mydb", 1, 5432, "any", "t"
        )
    )
    with patch.object(
        proxy,
        "add_proxy",
        return_value={
            "unit": "hop3-expose-postgres-mydb",
            "public_port": 54312,
            "target_port": 5432,
        },
    ):
        get_handler("proxy.add")(
            _req(
                "proxy.add",
                addon_type="postgres",
                addon_name="mydb",
                public_port=54312,
                target_port=5432,
                source="any",
            ),
            ctx,
        )
    assert len(ctx.state.proxies) == 1
    assert ctx.state.proxies[0].public_port == 54312


def test_add_rejects_bad_addon_name(ctx):
    with (
        patch.object(proxy, "add_proxy") as mock_add,
        pytest.raises(ValidationError),
    ):
        get_handler("proxy.add")(
            _req(
                "proxy.add",
                addon_type="postgres",
                addon_name="../etc",
                public_port=54312,
                target_port=5432,
            ),
            ctx,
        )
    mock_add.assert_not_called()


def test_add_rejects_bad_port(ctx):
    with pytest.raises(ValidationError):
        get_handler("proxy.add")(
            _req(
                "proxy.add",
                addon_type="postgres",
                addon_name="mydb",
                public_port=99999,
                target_port=5432,
            ),
            ctx,
        )


# --- proxy.remove --------------------------------------------------------


def test_remove_drops_state(ctx):
    ctx.state.proxies.append(
        StoredProxy(
            "redis", "cache", "hop3-expose-redis-cache", 54000, 6379, "any", "t"
        )
    )
    with patch.object(
        proxy,
        "remove_proxy",
        return_value={"removed": True, "unit": "hop3-expose-redis-cache"},
    ) as mock_rm:
        result = handler_remove(ctx, addon_type="redis", addon_name="cache")
    mock_rm.assert_called_once_with("hop3-expose-redis-cache")
    assert result["removed"] is True
    assert ctx.state.proxies == []
    assert ctx._saved["count"] == 1


def test_remove_idempotent_when_absent(ctx):
    with patch.object(
        proxy,
        "remove_proxy",
        return_value={"removed": False, "unit": "hop3-expose-redis-cache"},
    ):
        result = handler_remove(ctx, addon_type="redis", addon_name="cache")
    assert result["removed"] is False
    assert ctx.state.proxies == []


def handler_remove(ctx, **args):
    return get_handler("proxy.remove")(_req("proxy.remove", **args), ctx)


# --- proxy.list ----------------------------------------------------------


def test_list_returns_tracked_and_filters_by_type(ctx):
    ctx.state.proxies.extend([
        StoredProxy("postgres", "a", "hop3-expose-postgres-a", 54010, 5432, "any", "t"),
        StoredProxy("redis", "b", "hop3-expose-redis-b", 54011, 6379, "any", "t"),
    ])
    handler = get_handler("proxy.list")
    assert handler is not None

    all_proxies = handler(_req("proxy.list"), ctx)["proxies"]
    assert len(all_proxies) == 2

    pg_only = handler(_req("proxy.list", addon_type="postgres"), ctx)["proxies"]
    assert [p["addon_name"] for p in pg_only] == ["a"]
