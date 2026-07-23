# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for daemon ops (handshake, health)."""

from __future__ import annotations

from hop3_rootd import PROTOCOL_VERSION, __version__
from hop3_rootd.ops import all_ops, get_handler
from hop3_rootd.ops._base import OpContext
from hop3_rootd.protocol import Request
from hop3_rootd.state import State, StoredRule


def _ctx() -> OpContext:
    state = State()
    return OpContext(
        state=state,
        save_state=lambda: None,
        now_iso=lambda: "2026-04-24T15:30:00+00:00",
        new_rule_id=lambda: "rule-test",
    )


def test_version_is_a_nonempty_string():
    """
    Guard the symbol daemon.py re-exports for the handshake: the
    "prepare release 0.6.0" commit dropped `__version__` from the package while
    daemon.py still imported it, crash-looping rootd with an ImportError at
    daemon import (203/EXEC) and breaking every deploy. Keep it present.
    """
    assert isinstance(__version__, str)
    assert __version__


def test_registry_includes_daemon_ops():
    ops = all_ops()
    assert "daemon.handshake" in ops
    assert "daemon.health" in ops


def test_handshake_returns_versions():
    handler = get_handler("daemon.handshake")
    assert handler is not None
    req = Request(v=PROTOCOL_VERSION, id="r1", op="daemon.handshake", args={})
    result = handler(req, _ctx())
    assert result["daemon_version"] == __version__
    assert result["protocol_version"] == PROTOCOL_VERSION
    assert result["accepted"] is True


def test_handshake_accepts_optional_client_version():
    handler = get_handler("daemon.handshake")
    assert handler is not None
    req = Request(
        v=PROTOCOL_VERSION,
        id="r1",
        op="daemon.handshake",
        args={"client_version": "0.6.0", "client_protocol_version": 1},
    )
    result = handler(req, _ctx())
    assert result["accepted"] is True


def test_health_reports_basic_fields():
    handler = get_handler("daemon.health")
    assert handler is not None
    req = Request(v=PROTOCOL_VERSION, id="r1", op="daemon.health", args={})
    result = handler(req, _ctx())
    assert result["daemon_version"] == __version__
    assert result["protocol_version"] == PROTOCOL_VERSION
    assert "uptime_seconds" in result
    assert "rules_count" in result
    assert "errors_last_hour" in result
    assert result["rules_count"] == 0  # empty state


def test_health_reports_rules_count():
    handler = get_handler("daemon.health")
    assert handler is not None
    ctx = _ctx()
    # Add a fake rule to the state.
    ctx.state.rules.append(StoredRule("r1", {}, "2026-04-24T00:00:00Z"))
    req = Request(v=PROTOCOL_VERSION, id="r1", op="daemon.health", args={})
    result = handler(req, ctx)
    assert result["rules_count"] == 1


def test_health_uptime_is_nonnegative():
    handler = get_handler("daemon.health")
    assert handler is not None
    req = Request(v=PROTOCOL_VERSION, id="r1", op="daemon.health", args={})
    result = handler(req, _ctx())
    assert result["uptime_seconds"] >= 0
