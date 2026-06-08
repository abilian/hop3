# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: SIM105, TC003

"""Unit tests for the hop3-rootd client.

Uses a tmp Unix socket and a tiny in-process fake daemon (one thread
per connection running the protocol envelope by hand). End-to-end
testing of the real daemon lives in tests/c_system/.

Note: AF_UNIX socket paths are limited to ~104/107 chars on macOS/Linux,
so tests use a short tempdir under /tmp rather than pytest's tmp_path
(which can exceed the limit on macOS).
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from hop3.lib.rootd import (
    LocalRootdClient,
    RootdOpError,
    RootdProtocolError,
    RootdUnavailableError,
)


@pytest.fixture
def short_tmp_dir() -> Iterator[Path]:
    """Provide a tmpdir under /tmp (short path) for AF_UNIX sockets."""
    d = Path(tempfile.mkdtemp(prefix="rootd-", dir="/tmp"))
    try:
        yield d
    finally:
        for f in d.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
        os.rmdir(d)


# --- Fake daemon ----------------------------------------------------------


# In-process localhost AF_UNIX sockets answer in well under a millisecond, so
# this timeout only bounds how fast the daemon notices shutdown (the accept
# loop) or a dangling client connection (a refused-handshake test that leaves
# the socket half-open). 2.0s made every test pay ~2s in teardown; 0.25s keeps
# a generous margin while reclaiming it.
_SOCKET_TIMEOUT = 0.25


class FakeDaemon:
    """Tiny in-process daemon that speaks the rootd wire protocol.

    Configured with a `respond` callback (request dict → response dict).
    Runs in a background thread; tests should call .stop() in cleanup.
    """

    def __init__(self, socket_path: Path, respond):
        self.socket_path = socket_path
        self.respond = respond
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if socket_path.exists():
            socket_path.unlink()
        self._sock.bind(str(socket_path))
        self._sock.listen(2)
        self._sock.settimeout(_SOCKET_TIMEOUT)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stopping = False

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while not self._stopping:
            try:
                client, _ = self._sock.accept()
            except (TimeoutError, OSError):
                continue
            self._serve(client)

    def _serve(self, client: socket.socket) -> None:
        client.settimeout(_SOCKET_TIMEOUT)
        try:
            f = client.makefile("rb")
            while True:
                line = f.readline()
                if not line:
                    return
                try:
                    request = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    return
                response = self.respond(request)
                client.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except (TimeoutError, OSError):
            # The client went away (or stalled) after we answered — expected in
            # the negative tests where the client aborts on a refused handshake.
            # Exit the handler thread cleanly instead of letting the socket
            # timeout surface as an unhandled-thread-exception warning.
            return
        finally:
            try:
                client.close()
            except OSError:
                pass

    def stop(self) -> None:
        self._stopping = True
        try:
            self._sock.close()
        except OSError:
            pass
        self._thread.join(timeout=2.0)
        if self.socket_path.exists():
            self.socket_path.unlink()


@pytest.fixture
def daemon(short_tmp_dir) -> Iterator[FakeDaemon]:
    """Yield a fresh fake daemon. Test sets `daemon.respond = ...`."""
    socket_path = short_tmp_dir / "rootd.sock"
    d = FakeDaemon(socket_path, respond=_default_response)
    d.start()
    yield d
    d.stop()


def _default_response(request: dict) -> dict:
    """Default: handshake succeeds, anything else returns unknown_op."""
    if request.get("op") == "daemon.handshake":
        return {
            "v": 1,
            "id": request["id"],
            "ok": True,
            "result": {
                "daemon_version": "0.4.0",
                "protocol_version": 1,
                "accepted": True,
            },
        }
    return {
        "v": 1,
        "id": request["id"],
        "ok": False,
        "error": {"code": "unknown_op", "message": f"no such op: {request['op']}"},
    }


# --- Connection / handshake -----------------------------------------------


def test_connect_and_handshake_succeeds(daemon):
    client = LocalRootdClient(socket_path=daemon.socket_path)
    client.connect()
    assert client._sock is not None
    client.close()


def test_connect_fails_when_socket_missing(short_tmp_dir):
    """No socket file at all → RootdUnavailableError."""
    client = LocalRootdClient(socket_path=short_tmp_dir / "no-such-socket")
    with pytest.raises(RootdUnavailableError, match="not found"):
        client.connect()


def test_connect_fails_when_protocol_version_mismatches(short_tmp_dir):
    """Daemon claims a different protocol_version → RootdProtocolError."""
    socket_path = short_tmp_dir / "rootd.sock"

    def respond(request):
        return {
            "v": 1,
            "id": request["id"],
            "ok": True,
            "result": {
                "daemon_version": "0.6.0",
                "protocol_version": 999,  # mismatched
                "accepted": True,
            },
        }

    daemon = FakeDaemon(socket_path, respond=respond)
    daemon.start()
    try:
        client = LocalRootdClient(socket_path=socket_path)
        with pytest.raises(RootdProtocolError, match="protocol_version mismatch"):
            client.connect()
    finally:
        daemon.stop()


def test_connect_fails_when_daemon_refuses_handshake(short_tmp_dir):
    socket_path = short_tmp_dir / "rootd.sock"

    def respond(request):
        return {
            "v": 1,
            "id": request["id"],
            "ok": True,
            "result": {
                "daemon_version": "0.6.0",
                "protocol_version": 1,
                "accepted": False,
            },
        }

    daemon = FakeDaemon(socket_path, respond=respond)
    daemon.start()
    try:
        client = LocalRootdClient(socket_path=socket_path)
        with pytest.raises(RootdProtocolError, match="refused handshake"):
            client.connect()
    finally:
        daemon.stop()


# --- Op calls -------------------------------------------------------------


def test_call_returns_result_on_success(short_tmp_dir):
    socket_path = short_tmp_dir / "rootd.sock"

    def respond(request):
        if request["op"] == "daemon.handshake":
            return _default_response(request)
        return {
            "v": 1,
            "id": request["id"],
            "ok": True,
            "result": {"echo": request["args"]},
        }

    daemon = FakeDaemon(socket_path, respond=respond)
    daemon.start()
    try:
        with LocalRootdClient(socket_path=socket_path) as client:
            result = client.call("test.echo", {"hello": "world"})
        assert result == {"echo": {"hello": "world"}}
    finally:
        daemon.stop()


def test_call_raises_op_error_on_failure(daemon):
    """Default fake responds unknown_op for non-handshake ops."""
    with LocalRootdClient(socket_path=daemon.socket_path) as client:
        with pytest.raises(RootdOpError) as e:
            client.call("no.such.op", {})
        assert e.value.code == "unknown_op"


def test_call_handles_response_id_mismatch(short_tmp_dir):
    """Defense in depth: response id != request id → RootdProtocolError."""
    socket_path = short_tmp_dir / "rootd.sock"

    def respond(request):
        if request["op"] == "daemon.handshake":
            return _default_response(request)
        return {
            "v": 1,
            "id": "WRONG",
            "ok": True,
            "result": {},
        }

    daemon = FakeDaemon(socket_path, respond=respond)
    daemon.start()
    try:
        with (
            LocalRootdClient(socket_path=socket_path) as client,
            pytest.raises(RootdProtocolError, match="id mismatch"),
        ):
            client.call("test.foo", {})
    finally:
        daemon.stop()


def test_call_handles_invalid_json_response(short_tmp_dir):
    """Daemon writes malformed JSON → RootdProtocolError."""
    socket_path = short_tmp_dir / "rootd.sock"

    request_count = {"n": 0}

    def respond(request):
        request_count["n"] += 1
        if request_count["n"] == 1:  # handshake — must succeed
            return _default_response(request)
        # Subsequent: garbage, broken envelope
        return "not a dict"  # type: ignore[return-value]

    # We can't easily inject raw garbage through our FakeDaemon's JSON path,
    # so this test is an artificial scenario — kept for coverage of the
    # decode-time error path. The fake just returns non-dict which serialises
    # to `"not a dict"\n`, which json.loads can read but we expect dict.
    daemon = FakeDaemon(socket_path, respond=respond)
    daemon.start()
    try:
        with (
            LocalRootdClient(socket_path=socket_path) as client,
            pytest.raises(RootdProtocolError),
        ):
            client.call("test.foo", {})
    finally:
        daemon.stop()


def test_call_can_be_invoked_multiple_times_on_same_connection(daemon):
    daemon.respond = lambda req: (
        _default_response(req)
        if req["op"] == "daemon.handshake"
        else {
            "v": 1,
            "id": req["id"],
            "ok": True,
            "result": {"n": req["args"].get("n")},
        }
    )
    with LocalRootdClient(socket_path=daemon.socket_path) as client:
        for i in range(5):
            result = client.call("test.echo", {"n": i})
            assert result == {"n": i}


def test_close_is_idempotent(daemon):
    client = LocalRootdClient(socket_path=daemon.socket_path)
    client.connect()
    client.close()
    client.close()  # no error


def test_context_manager_closes_on_exit(daemon):
    with LocalRootdClient(socket_path=daemon.socket_path) as client:
        assert client._sock is not None
    assert client._sock is None
