# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""Wire protocol for hop3-rootd.

Line-delimited JSON over a Unix domain socket. One JSON object per
line, terminated with `\\n`. Both sides write `json.dumps(obj) + "\\n"`
and read with `socket.makefile().readline()`.

See ADR 041 §3 for the full protocol specification.

Envelope (request):

    {"v": 1, "id": "<uuid4>", "op": "firewall.add_rule", "args": {...}}

Envelope (response, success):

    {"v": 1, "id": "<uuid4>", "ok": true, "result": {...}}

Envelope (response, error):

    {"v": 1, "id": "<uuid4>", "ok": false,
     "error": {"code": "...", "message": "..."}}
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from hop3_rootd import PROTOCOL_VERSION


class ErrorCode(str, Enum):
    """Fixed enum of error codes the daemon can return.

    New codes are added per op. Adding a new code is part of the protocol
    contract; clients gracefully treat unknown codes as opaque errors.
    """

    PROTOCOL_VERSION_MISMATCH = "protocol_version_mismatch"
    UNKNOWN_OP = "unknown_op"
    MALFORMED_REQUEST = "malformed_request"
    VALIDATION_FAILED = "validation_failed"
    STATE_CONFLICT = "state_conflict"
    KERNEL_ERROR = "kernel_error"
    LOCKDOWN_ACTIVE = "lockdown_active"  # reserved for future use
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class Request:
    """Parsed request envelope."""

    v: int
    id: str
    op: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Response:
    """Response envelope. Either `result` or `error` is set, never both."""

    v: int
    id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"v": self.v, "id": self.id, "ok": self.ok}
        if self.ok:
            out["result"] = self.result if self.result is not None else {}
        else:
            out["error"] = self.error if self.error is not None else {}
        return out


class ProtocolError(Exception):
    """Raised when a request cannot be parsed into a Request.

    The error code identifies which kind of malformedness:
    `MALFORMED_REQUEST` for missing/wrong-type fields,
    `PROTOCOL_VERSION_MISMATCH` for version skew.
    """

    def __init__(self, code: ErrorCode, message: str, request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id


# --- Encoding --------------------------------------------------------------


def encode_response(resp: Response) -> bytes:
    """Encode a response envelope as bytes for socket write.

    Trailing `\\n` is included; one full message per call.
    """
    return (json.dumps(resp.to_dict(), separators=(",", ":")) + "\n").encode("utf-8")


def encode_request(
    *, op: str, args: dict[str, Any], request_id: str, v: int = PROTOCOL_VERSION
) -> bytes:
    """Encode a request envelope as bytes. Used by the client side.

    Bare-keyword args to make caller intent explicit.
    """
    obj = {"v": v, "id": request_id, "op": op, "args": args}
    return (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")


# --- Decoding --------------------------------------------------------------


def _parse_json_object(line: bytes | str) -> dict[str, Any]:
    """Decode bytes/str → JSON object, raising ProtocolError on any failure."""
    if isinstance(line, bytes):
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ProtocolError(
                ErrorCode.MALFORMED_REQUEST, f"non-utf-8 bytes: {e}"
            ) from e
    else:
        text = line

    text = text.rstrip("\n")
    if not text:
        raise ProtocolError(ErrorCode.MALFORMED_REQUEST, "empty line")

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ProtocolError(ErrorCode.MALFORMED_REQUEST, f"invalid JSON: {e}") from e

    if not isinstance(obj, dict):
        raise ProtocolError(
            ErrorCode.MALFORMED_REQUEST, "request must be a JSON object"
        )

    return obj


def _validate_version(obj: dict[str, Any], request_id: str | None) -> int:
    """Extract and check the protocol version. Raises on mismatch."""
    v = obj.get("v")
    if not isinstance(v, int):
        raise ProtocolError(
            ErrorCode.MALFORMED_REQUEST,
            "missing or non-integer 'v' (protocol version)",
            request_id=request_id,
        )
    if v != PROTOCOL_VERSION:
        raise ProtocolError(
            ErrorCode.PROTOCOL_VERSION_MISMATCH,
            f"client v={v}, daemon v={PROTOCOL_VERSION}",
            request_id=request_id,
        )
    return v


def decode_request(line: bytes | str) -> Request:
    """Parse one line of bytes/text into a Request.

    Raises ProtocolError on:
      - non-JSON or non-object payload (MALFORMED_REQUEST)
      - missing required fields (MALFORMED_REQUEST)
      - wrong field types (MALFORMED_REQUEST)
      - protocol-version mismatch (PROTOCOL_VERSION_MISMATCH)

    The request_id is preserved on the exception when extractable, so
    the caller can build a response that echoes the id back.
    """
    obj = _parse_json_object(line)

    # Recover the id early even if other fields are bad, so we can echo it.
    request_id = obj.get("id") if isinstance(obj.get("id"), str) else None

    v = _validate_version(obj, request_id)

    if not isinstance(request_id, str) or not request_id:
        raise ProtocolError(
            ErrorCode.MALFORMED_REQUEST,
            "missing or empty 'id' (request_id)",
        )

    op = obj.get("op")
    if not isinstance(op, str) or not op:
        raise ProtocolError(
            ErrorCode.MALFORMED_REQUEST,
            "missing or empty 'op' (operation name)",
            request_id=request_id,
        )

    args = obj.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ProtocolError(
            ErrorCode.MALFORMED_REQUEST,
            "'args' must be a JSON object",
            request_id=request_id,
        )

    return Request(v=v, id=request_id, op=op, args=args)


# --- Helpers for building responses ----------------------------------------


def success(req: Request, result: dict[str, Any] | None = None) -> Response:
    """Build a success response echoing the request id and version."""
    return Response(v=req.v, id=req.id, ok=True, result=result or {})


def error_response(
    request_id: str | None,
    code: ErrorCode | str,
    message: str,
    v: int = PROTOCOL_VERSION,
) -> Response:
    """Build an error response.

    `request_id` is None when the request couldn't be parsed enough to
    extract an id; clients are tolerant of this case.
    """
    code_str = code.value if isinstance(code, ErrorCode) else code
    return Response(
        v=v,
        id=request_id or "",
        ok=False,
        error={"code": code_str, "message": message},
    )


def error_from_protocol_error(exc: ProtocolError) -> Response:
    """Convenience: build an error Response from a raised ProtocolError."""
    return error_response(exc.request_id, exc.code, exc.message)


# Constants exported for tests and other modules ----------------------------

HANDSHAKE_OP: Final[str] = "daemon.handshake"
HEALTH_OP: Final[str] = "daemon.health"
