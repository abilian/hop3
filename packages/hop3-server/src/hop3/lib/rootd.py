# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, raw-string-in-exception, f-string-in-exception, suppressible-exception, typing-only-standard-library-import]

"""
Client for the hop3-rootd Unix socket.

`LocalRootdClient` connects to /run/hop3-rootd/socket, performs the
mandatory `daemon.handshake`, and exposes `call(op, args)` for op
invocations. Used by the firewall and nginx plugins on the hop3-server
side.

See ADR 041 §3 (IPC protocol) and §11 (versioning).
"""

from __future__ import annotations

import json
import socket
import uuid
from importlib.metadata import PackageNotFoundError, version
from io import BufferedReader
from pathlib import Path
from typing import Any, Final, Self

# --- Constants ------------------------------------------------------------

DEFAULT_SOCKET_PATH: Final[Path] = Path("/run/hop3-rootd/socket")

# Wire-protocol version. Must match the daemon's PROTOCOL_VERSION.
# Bumped in lockstep with the daemon — see ADR 041 §11.
PROTOCOL_VERSION: Final[int] = 1

# Wire error code the daemon returns on protocol-version skew (mirrors
# hop3_rootd.protocol.ErrorCode.PROTOCOL_VERSION_MISMATCH). Kept as a local
# literal rather than imported, so the client carries no hop3-rootd dependency.
_PROTOCOL_VERSION_MISMATCH_CODE: Final[str] = "protocol_version_mismatch"

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0


# --- Exceptions -----------------------------------------------------------


class RootdError(Exception):
    """Base for any error from the rootd client."""


class RootdUnavailableError(RootdError):
    """
    Couldn't reach the daemon (socket missing, permission denied,
    connection refused). Treated as a deploy-blocker.
    """


class RootdProtocolError(RootdError):
    """Wire-level mismatch (bad JSON, missing fields, version skew)."""


class RootdOpError(RootdError):
    """
    Op completed but returned an error envelope.

    The `code` field is one of the `ErrorCode` values defined in the
    daemon (validation_failed, kernel_error, state_conflict, etc.).
    Callers can branch on `code` for different recovery paths.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"rootd op error [{code}]: {message}")
        self.code = code
        self.message = message


# --- Client ---------------------------------------------------------------


class LocalRootdClient:
    """
    One-connection, one-thread client for hop3-rootd.

    Use as a context manager:

        with LocalRootdClient() as client:
            result = client.call("firewall.add_rule", {...})

    The handshake is performed automatically on first use. The
    connection is closed on exit.
    """

    def __init__(
        self,
        socket_path: Path = DEFAULT_SOCKET_PATH,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.socket_path = socket_path
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._reader: BufferedReader | None = None  # file-like wrapper for line reads

    # --- Connection lifecycle --------------------------------------------

    def connect(self) -> None:
        """Open the socket and perform the handshake."""
        if self._sock is not None:
            return
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect(str(self.socket_path))
        except FileNotFoundError as e:
            raise RootdUnavailableError(
                f"hop3-rootd socket not found at {self.socket_path}; "
                "is the daemon running?"
            ) from e
        except (OSError, ConnectionError) as e:
            raise RootdUnavailableError(
                f"could not connect to hop3-rootd at {self.socket_path}: {e}"
            ) from e

        self._sock = sock
        self._reader = sock.makefile("rb")
        self._handshake()

    def close(self) -> None:
        """Close the connection. Idempotent."""
        if self._reader is not None:
            try:
                self._reader.close()
            except OSError:
                pass
            self._reader = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # --- Handshake -------------------------------------------------------

    def _handshake(self) -> None:
        """
        Send daemon.handshake and validate the response.

        Version skew is surfaced as RootdProtocolError with the actionable
        remediation ADR 041 §3 promises, via two paths:

        - The real daemon validates the protocol version of *every* envelope
          at decode time (each message carries ``v``), so a skew comes back as
          a ``protocol_version_mismatch`` error envelope — which ``_send_recv``
          raises as ``RootdOpError`` — before any handshake body exists. That is
          the path a real mismatch takes; translate it here.
        - Defense in depth: a daemon that answered ``ok=True`` but with a
          mismatched ``protocol_version`` in the body is caught by the explicit
          check below.
        """
        try:
            result = self._send_recv(
                "daemon.handshake",
                {
                    "client_version": _client_version(),
                    "client_protocol_version": PROTOCOL_VERSION,
                },
            )
        except RootdOpError as e:
            if e.code == _PROTOCOL_VERSION_MISMATCH_CODE:
                raise RootdProtocolError(
                    f"protocol_version mismatch ({e.message}); "
                    "re-run hop3-install server to upgrade hop3-rootd"
                ) from e
            raise

        # daemon.handshake returns: {daemon_version, protocol_version, accepted}
        daemon_pv = result.get("protocol_version")
        if daemon_pv != PROTOCOL_VERSION:
            raise RootdProtocolError(
                f"protocol_version mismatch: client={PROTOCOL_VERSION}, "
                f"daemon={daemon_pv}; re-run hop3-install server to upgrade"
            )
        if not result.get("accepted", False):
            raise RootdProtocolError(f"daemon refused handshake: {result}")

    # --- Op call (public API) --------------------------------------------

    def call(self, op: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Invoke `op` with `args`. Returns the result dict on success.

        Raises RootdOpError on a daemon-side error.
        Raises RootdUnavailableError / RootdProtocolError on transport
        problems.
        """
        if self._sock is None:
            self.connect()
        return self._send_recv(op, args or {})

    # --- Internals --------------------------------------------------------

    def _send_recv(self, op: str, args: dict[str, Any]) -> dict[str, Any]:
        """Single request/response round trip."""
        if self._sock is None or self._reader is None:
            raise RootdUnavailableError("not connected")

        request_id = uuid.uuid4().hex
        envelope = {
            "v": PROTOCOL_VERSION,
            "id": request_id,
            "op": op,
            "args": args,
        }
        line = (json.dumps(envelope, separators=(",", ":")) + "\n").encode("utf-8")

        try:
            self._sock.sendall(line)
        except OSError as e:
            raise RootdUnavailableError(f"send failed: {e}") from e

        try:
            response_bytes = self._reader.readline()
        except OSError as e:
            raise RootdUnavailableError(f"recv failed: {e}") from e

        if not response_bytes:
            raise RootdUnavailableError("daemon closed connection without responding")

        try:
            response = json.loads(response_bytes.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise RootdProtocolError(
                f"could not parse response: {e}; raw: {response_bytes!r}"
            ) from e

        if not isinstance(response, dict):
            raise RootdProtocolError(
                f"response should be a JSON object, got {type(response).__name__}"
            )

        # Check id echo (defense in depth — single-threaded client, but
        # better to fail loudly if something's wrong).
        if response.get("id") != request_id:
            raise RootdProtocolError(
                f"response id mismatch: sent {request_id!r}, got {response.get('id')!r}"
            )

        if response.get("ok"):
            result = response.get("result", {})
            if not isinstance(result, dict):
                raise RootdProtocolError(
                    f"response 'result' should be object, got {type(result).__name__}"
                )
            return result

        # Error path.
        err = response.get("error", {})
        code = err.get("code", "unknown")
        message = err.get("message", "(no message)")
        raise RootdOpError(code, message)


def _client_version() -> str:
    """
    Return the hop3-server version (best-effort).

    Not essential — the daemon doesn't gate on this. We just send it
    for diagnostics in the audit log.
    """
    try:
        return version("hop3-server")
    except PackageNotFoundError:
        return "unknown"
