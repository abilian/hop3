# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the server's dispatcher.

Tests dispatch() and handle_one() in isolation — no actual sockets here.
End-to-end tests live in tests/b_integration/ where real Unix sockets +
real nft are available.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from hop3_rootd import PROTOCOL_VERSION, server as srv
from hop3_rootd.audit import AuditLog
from hop3_rootd.ops import OpRegistration
from hop3_rootd.ops._base import OpContext
from hop3_rootd.ops.nginx import (
    NginxBinaryNotFoundError,
    NginxReloadNotAppliedError,
)
from hop3_rootd.protocol import ErrorCode, Request, decode_request, encode_request
from hop3_rootd.server import dispatch, handle_one
from hop3_rootd.state import State, StoredRule

from tests.a_unit._fakes import FakeExec, fail, ok


def _ctx_for(state: State):
    return OpContext(
        state=state,
        save_state=lambda: None,
        now_iso=lambda: "2026-04-24T15:30:00+00:00",
        new_rule_id=lambda: "rule-x",
        exec=FakeExec(),
    )


# --- dispatch() -----------------------------------------------------------


def test_dispatch_unknown_op():
    state = State()
    req = Request(v=PROTOCOL_VERSION, id="r1", op="no.such.op", args={})
    resp = dispatch(req, _ctx_for(state))
    assert not resp.ok
    err = resp.error
    assert err is not None
    assert err["code"] == ErrorCode.UNKNOWN_OP.value


def test_dispatch_health_succeeds():
    state = State()
    req = Request(v=PROTOCOL_VERSION, id="r1", op="daemon.health", args={})
    resp = dispatch(req, _ctx_for(state))
    assert resp.ok
    result = resp.result
    assert result is not None
    assert "uptime_seconds" in result


def test_dispatch_handshake_succeeds():
    state = State()
    req = Request(v=PROTOCOL_VERSION, id="r1", op="daemon.handshake", args={})
    resp = dispatch(req, _ctx_for(state))
    assert resp.ok
    result = resp.result
    assert result is not None
    assert result["accepted"] is True


def test_dispatch_validation_error_returns_validation_failed_code():
    state = State()
    req = Request(
        v=PROTOCOL_VERSION,
        id="r1",
        op="firewall.add_rule",
        args={"port": 99999, "protocol": "tcp", "source": "any", "app_name": "x"},
    )
    resp = dispatch(req, _ctx_for(state))
    assert not resp.ok
    err = resp.error
    assert err is not None
    assert err["code"] == ErrorCode.VALIDATION_FAILED.value


def test_dispatch_state_conflict_returns_state_conflict_code():
    state = State()
    req = Request(
        v=PROTOCOL_VERSION,
        id="r1",
        op="firewall.remove_rule",
        args={"rule_id": "no-such-rule"},
    )
    resp = dispatch(req, _ctx_for(state))
    assert not resp.ok
    err = resp.error
    assert err is not None
    assert err["code"] == ErrorCode.STATE_CONFLICT.value


def test_dispatch_kernel_error_returns_kernel_error_code():
    """nft failure surfaces as kernel_error."""
    state = State()
    ctx = _ctx_for(state)
    ctx.exec.on(lambda argv: True, fail("Error: bad rule"))
    req = Request(
        v=PROTOCOL_VERSION,
        id="r1",
        op="firewall.add_rule",
        args={"port": 8448, "protocol": "tcp", "source": "any", "app_name": "matrix"},
    )
    resp = dispatch(req, ctx)

    assert not resp.ok
    err = resp.error
    assert err is not None
    assert err["code"] == ErrorCode.KERNEL_ERROR.value


def test_dispatch_nginx_reload_not_applied_is_kernel_error_with_reason():
    """
    A rejected nginx reload → kernel_error with the actionable reason kept in
    the message (NOT scrubbed to the opaque internal_error). This is the whole
    point of adding the nginx errors to the KERNEL_ERROR tuple — pin it.
    """
    state = State()
    req = Request(v=PROTOCOL_VERSION, id="r1", op="nginx.reload", args={})
    reason = "[emerg] bind() to 127.0.0.1:8443 failed (98: Address already in use)"

    def rejecting_handler(_req, _ctx):
        msg = f"did not apply the new config: {reason}"
        raise NginxReloadNotAppliedError(msg)

    fake_reg = OpRegistration(handler=rejecting_handler, audit=True)
    with patch.object(srv, "get_registration", return_value=fake_reg):
        resp = dispatch(req, _ctx_for(state))

    assert not resp.ok
    err = resp.error
    assert err is not None
    assert err["code"] == ErrorCode.KERNEL_ERROR.value
    assert "bind() to 127.0.0.1:8443" in err["message"]  # reason survives


def test_dispatch_nginx_binary_not_found_is_kernel_error():
    state = State()
    req = Request(v=PROTOCOL_VERSION, id="r1", op="nginx.reload", args={})

    def no_method_handler(_req, _ctx):
        msg = "no nginx-reload method available"
        raise NginxBinaryNotFoundError(msg)

    fake_reg = OpRegistration(handler=no_method_handler, audit=True)
    with patch.object(srv, "get_registration", return_value=fake_reg):
        resp = dispatch(req, _ctx_for(state))

    assert not resp.ok
    assert resp.error is not None
    assert resp.error["code"] == ErrorCode.KERNEL_ERROR.value


def test_dispatch_unexpected_exception_returns_internal_error():
    """Any other exception → internal_error with opaque message."""
    state = State()
    req = Request(v=PROTOCOL_VERSION, id="r1", op="daemon.health", args={})

    def broken_handler(_req, _ctx):
        msg = "unexpected boom"
        raise RuntimeError(msg)

    fake_reg = OpRegistration(handler=broken_handler, audit=False)
    with patch.object(srv, "get_registration", return_value=fake_reg):
        resp = dispatch(req, _ctx_for(state))

    assert not resp.ok
    err = resp.error
    assert err is not None
    assert err["code"] == ErrorCode.INTERNAL_ERROR.value


# --- handle_one (with audit) ---------------------------------------------


def test_handle_one_success_writes_audit_for_mutating_op(tmp_path):
    """Mutating ops (audit=True) write an audit entry on success."""
    audit_path = tmp_path / "audit.log"
    audit = AuditLog(audit_path)
    state = State()
    ctx = _ctx_for(state)
    ctx.exec.on(
        lambda argv: "list" in argv,
        ok(stdout='{"nftables":[{"rule":{"handle":47,"comment":"hop3:rule:rule-x"}}]}'),
    )

    line = encode_request(
        op="firewall.add_rule",
        args={
            "port": 8448,
            "protocol": "tcp",
            "source": "any",
            "app_name": "matrix-fed",
        },
        request_id="r1",
    )
    response_bytes = handle_one(line, ctx, audit, caller_uid=1000)
    audit.close()

    parsed = json.loads(response_bytes.decode().rstrip("\n"))
    assert parsed["ok"] is True

    audit_entry = json.loads(audit_path.read_text().strip())
    assert audit_entry["request_id"] == "r1"
    assert audit_entry["op"] == "firewall.add_rule"
    assert audit_entry["outcome"] == "applied"
    assert audit_entry["caller_uid"] == 1000


def test_handle_one_success_skips_audit_for_readonly_op(tmp_path):
    """Read-only ops (audit=False) succeed but write nothing to audit log."""
    audit_path = tmp_path / "audit.log"
    audit = AuditLog(audit_path)
    state = State()
    line = encode_request(op="daemon.health", args={}, request_id="r1")

    response_bytes = handle_one(line, _ctx_for(state), audit, caller_uid=1000)
    audit.close()

    parsed = json.loads(response_bytes.decode().rstrip("\n"))
    assert parsed["ok"] is True
    # daemon.health is registered audit=False — no audit entry written.
    assert not audit_path.exists() or audit_path.read_text() == ""


def test_handle_one_validation_error_writes_audit(tmp_path):
    audit_path = tmp_path / "audit.log"
    audit = AuditLog(audit_path)
    state = State()
    line = encode_request(
        op="firewall.add_rule",
        args={"port": 99999, "protocol": "tcp", "source": "any", "app_name": "x"},
        request_id="r-bad",
    )

    handle_one(line, _ctx_for(state), audit, caller_uid=1000)
    audit.close()

    audit_entry = json.loads(audit_path.read_text().strip())
    assert audit_entry["outcome"] == "error"
    assert audit_entry["error"]["code"] == "validation_failed"


def test_handle_one_protocol_error_writes_audit(tmp_path):
    """Even a malformed line (can't be decoded) gets an audit entry."""
    audit_path = tmp_path / "audit.log"
    audit = AuditLog(audit_path)
    state = State()

    handle_one(b"not json", _ctx_for(state), audit, caller_uid=1000)
    audit.close()

    audit_entry = json.loads(audit_path.read_text().strip())
    assert audit_entry["outcome"] == "error"
    assert audit_entry["error"]["code"] == "malformed_request"
    assert audit_entry["op"] == "(undecoded)"


def test_handle_one_redacts_secret_args_in_error_path(tmp_path):
    """
    Sanitisation: token/password/secret fields in args are redacted in audit.

    Uses an error path on a mutating op so the audit fires regardless of
    audit=True/False on the op (errors always audit).
    """
    audit_path = tmp_path / "audit.log"
    audit = AuditLog(audit_path)
    state = State()
    # firewall.add_rule will fail validation on the bogus port; the
    # request payload (including the secret) is still sanitised in audit.
    line = encode_request(
        op="firewall.add_rule",
        args={
            "port": 99999,
            "protocol": "tcp",
            "source": "any",
            "app_name": "myapp",
            "client_secret": "hunter2",
        },
        request_id="r1",
    )

    handle_one(line, _ctx_for(state), audit, caller_uid=1000)
    audit.close()

    audit_entry = json.loads(audit_path.read_text().strip())
    assert audit_entry["args"]["client_secret"] == "<redacted>"
    assert audit_entry["args"]["app_name"] == "myapp"


def test_handle_one_protocol_version_mismatch(tmp_path):
    """v=999 → protocol_version_mismatch with the same id echoed back."""
    audit_path = tmp_path / "audit.log"
    audit = AuditLog(audit_path)
    state = State()
    line = (
        json.dumps({"v": 999, "id": "r1", "op": "daemon.health", "args": {}}).encode()
        + b"\n"
    )

    response_bytes = handle_one(line, _ctx_for(state), audit, caller_uid=1000)
    audit.close()

    parsed = json.loads(response_bytes.decode().rstrip("\n"))
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "protocol_version_mismatch"
    assert parsed["id"] == "r1"  # id echoed despite version mismatch


# --- Round-trip through encode/decode ------------------------------------


def test_handle_one_round_trip(tmp_path):
    audit = AuditLog(tmp_path / "audit.log")
    state = State()
    state.rules.append(
        StoredRule(
            rule_id="r1",
            spec={"app_name": "matrix", "port": 8448},
            applied_at="2026-04-24T00:00:00Z",
        )
    )
    line = encode_request(op="firewall.list_rules", args={}, request_id="req-1")

    response_bytes = handle_one(line, _ctx_for(state), audit, caller_uid=1000)
    audit.close()

    # Response can be decoded as a Response (using the protocol's decoder
    # in reverse — for tests we just JSON-parse and check shape).
    parsed = json.loads(response_bytes.decode().rstrip("\n"))
    assert parsed["ok"] is True
    assert parsed["id"] == "req-1"
    assert len(parsed["result"]["rules"]) == 1
    assert parsed["result"]["rules"][0]["rule_id"] == "r1"


def test_decode_round_trip_via_dispatch():
    """Encode → decode → dispatch, end to end without sockets."""
    state = State()
    raw = encode_request(op="daemon.handshake", args={}, request_id="x")
    req = decode_request(raw)
    resp = dispatch(req, _ctx_for(state))
    assert resp.ok
    assert resp.id == "x"
