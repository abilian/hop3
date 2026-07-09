# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the wire protocol."""

from __future__ import annotations

import json

import pytest
from hop3_rootd import PROTOCOL_VERSION
from hop3_rootd.protocol import (
    ErrorCode,
    ProtocolError,
    Response,
    decode_request,
    encode_request,
    encode_response,
    error_from_protocol_error,
    error_response,
    success,
)

# --- Round-trip encoding / decoding ---------------------------------------


def test_encode_request_emits_one_json_line():
    raw = encode_request(op="firewall.add_rule", args={"port": 8448}, request_id="abc")
    assert raw.endswith(b"\n")
    obj = json.loads(raw[:-1].decode())
    assert obj == {
        "v": PROTOCOL_VERSION,
        "id": "abc",
        "op": "firewall.add_rule",
        "args": {"port": 8448},
    }


def test_encode_response_success():
    resp = Response(v=1, id="abc", ok=True, result={"rule_id": "r-1"})
    raw = encode_response(resp)
    assert raw.endswith(b"\n")
    obj = json.loads(raw[:-1].decode())
    assert obj == {"v": 1, "id": "abc", "ok": True, "result": {"rule_id": "r-1"}}


def test_encode_response_error():
    resp = Response(
        v=1, id="abc", ok=False, error={"code": "validation_failed", "message": "x"}
    )
    raw = encode_response(resp)
    obj = json.loads(raw[:-1].decode())
    assert obj == {
        "v": 1,
        "id": "abc",
        "ok": False,
        "error": {"code": "validation_failed", "message": "x"},
    }


def test_encode_response_omits_unset_fields():
    """Success response without result still emits empty result dict."""
    resp = Response(v=1, id="abc", ok=True, result=None)
    obj = json.loads(encode_response(resp)[:-1].decode())
    assert obj == {"v": 1, "id": "abc", "ok": True, "result": {}}


def test_round_trip():
    raw = encode_request(
        op="daemon.handshake", args={"client_version": "0.6.0"}, request_id="r1"
    )
    req = decode_request(raw)
    assert req.id == "r1"
    assert req.op == "daemon.handshake"
    assert req.args == {"client_version": "0.6.0"}
    assert req.v == PROTOCOL_VERSION


# --- Decoding errors ------------------------------------------------------


def test_decode_empty_line_raises_malformed():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(b"")
    assert exc_info.value.code == ErrorCode.MALFORMED_REQUEST


def test_decode_non_json_raises_malformed():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(b"not json\n")
    assert exc_info.value.code == ErrorCode.MALFORMED_REQUEST
    assert "invalid JSON" in exc_info.value.message


def test_decode_non_object_raises_malformed():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(b'["array", "not", "object"]\n')
    assert exc_info.value.code == ErrorCode.MALFORMED_REQUEST
    assert "JSON object" in exc_info.value.message


def test_decode_non_utf8_raises_malformed():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(b"\xff\xfe not utf-8\n")
    assert exc_info.value.code == ErrorCode.MALFORMED_REQUEST


def test_decode_missing_v_raises_malformed():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(json.dumps({"id": "r1", "op": "x", "args": {}}).encode())
    assert exc_info.value.code == ErrorCode.MALFORMED_REQUEST
    assert "'v'" in exc_info.value.message


def test_decode_v_must_be_int():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(
            json.dumps({"v": "1", "id": "r1", "op": "x", "args": {}}).encode()
        )
    assert exc_info.value.code == ErrorCode.MALFORMED_REQUEST


def test_decode_version_mismatch():
    """When v parses but doesn't match the daemon's PROTOCOL_VERSION."""
    bogus_version = PROTOCOL_VERSION + 99
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(
            json.dumps({"v": bogus_version, "id": "r1", "op": "x", "args": {}}).encode()
        )
    assert exc_info.value.code == ErrorCode.PROTOCOL_VERSION_MISMATCH
    # The id should be preserved on the exception so the daemon can echo it.
    assert exc_info.value.request_id == "r1"


def test_decode_missing_id_raises_malformed():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(
            json.dumps({"v": PROTOCOL_VERSION, "op": "x", "args": {}}).encode()
        )
    assert exc_info.value.code == ErrorCode.MALFORMED_REQUEST


def test_decode_empty_id_raises_malformed():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(
            json.dumps({
                "v": PROTOCOL_VERSION,
                "id": "",
                "op": "x",
                "args": {},
            }).encode()
        )
    assert exc_info.value.code == ErrorCode.MALFORMED_REQUEST


def test_decode_missing_op_raises_malformed():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(
            json.dumps({"v": PROTOCOL_VERSION, "id": "r1", "args": {}}).encode()
        )
    assert exc_info.value.code == ErrorCode.MALFORMED_REQUEST
    assert exc_info.value.request_id == "r1"


def test_decode_args_default_to_empty_dict_when_missing():
    """Missing 'args' is allowed; defaults to {}."""
    req = decode_request(
        json.dumps({"v": PROTOCOL_VERSION, "id": "r1", "op": "daemon.health"}).encode()
    )
    assert req.args == {}


def test_decode_non_object_args_raises_malformed():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(
            json.dumps({
                "v": PROTOCOL_VERSION,
                "id": "r1",
                "op": "x",
                "args": "string",
            }).encode()
        )
    assert exc_info.value.code == ErrorCode.MALFORMED_REQUEST


def test_decode_strips_trailing_newline():
    req = decode_request(b'{"v":1,"id":"r1","op":"x","args":{}}\n')
    assert req.id == "r1"


def test_decode_accepts_str_input():
    req = decode_request('{"v":1,"id":"r1","op":"x","args":{}}\n')
    assert req.id == "r1"


# --- Response builders ----------------------------------------------------


def test_success_echoes_id_and_version():
    req = decode_request(b'{"v":1,"id":"r1","op":"x","args":{}}\n')
    resp = success(req, {"hello": "world"})
    assert resp.ok
    assert resp.id == "r1"
    assert resp.v == 1
    assert resp.result == {"hello": "world"}
    assert resp.error is None


def test_success_with_no_result():
    req = decode_request(b'{"v":1,"id":"r1","op":"x","args":{}}\n')
    resp = success(req)
    assert resp.result == {}


def test_error_response_with_known_code():
    resp = error_response("r1", ErrorCode.VALIDATION_FAILED, "bad port")
    assert not resp.ok
    assert resp.id == "r1"
    assert resp.error == {"code": "validation_failed", "message": "bad port"}


def test_error_response_with_string_code():
    """Future or unknown codes can be passed as strings."""
    resp = error_response("r1", "future_code", "...")
    assert resp.error == {"code": "future_code", "message": "..."}


def test_error_response_with_no_id():
    """When id couldn't be extracted, response carries empty string."""
    resp = error_response(None, ErrorCode.MALFORMED_REQUEST, "...")
    assert resp.id == ""


def test_error_from_protocol_error_preserves_id():
    """A ProtocolError raised mid-decode carries the recovered id."""
    exc = ProtocolError(ErrorCode.PROTOCOL_VERSION_MISMATCH, "skew", request_id="r1")
    resp = error_from_protocol_error(exc)
    assert resp.id == "r1"
    assert resp.error == {"code": "protocol_version_mismatch", "message": "skew"}


def test_error_from_protocol_error_no_id():
    exc = ProtocolError(ErrorCode.MALFORMED_REQUEST, "...")
    resp = error_from_protocol_error(exc)
    assert resp.id == ""


# --- Envelope invariant ---------------------------------------------------


def test_response_rejects_ok_with_error():
    """ok=True must not carry an error — to_dict() would emit a malformed envelope."""
    with pytest.raises(ValueError):
        Response(v=1, id="r1", ok=True, error={"code": "x", "message": "y"})


def test_response_rejects_error_with_result():
    """ok=False must not carry a result."""
    with pytest.raises(ValueError):
        Response(v=1, id="r1", ok=False, result={"some": "value"})
