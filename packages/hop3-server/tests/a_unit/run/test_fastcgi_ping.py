# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The readiness probe for a backend that speaks FastCGI, not HTTP.

The gate it feeds requires evidence a *worker* answered — a master binds its
listen socket before forking, so a bare `connect()` proves nothing. These
drive a real socket rather than a stubbed one, because the thing being tested
is whether we encode and parse records the way php-fpm does.
"""

from __future__ import annotations

import socket
import struct
import threading
from contextlib import closing

import pytest

from hop3.run.fastcgi import FCGI_PING_PATH, fastcgi_ping

HEADER = struct.Struct("!BBHHBB")
TYPE_STDOUT = 6
TYPE_END_REQUEST = 3
PONG = b"Content-Type: text/plain\r\nContent-Length: 4\r\n\r\npong"


def record(record_type: int, content: bytes, request_id: int = 1) -> bytes:
    return HEADER.pack(1, record_type, request_id, len(content), 0, 0) + content


class FakeResponder:
    """A socket server that answers one FastCGI request the way php-fpm does."""

    def __init__(self, reply: bytes | None, split_at: int | None = None) -> None:
        self.reply = reply
        self.split_at = split_at
        self.request = b""
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        with closing(conn):
            conn.settimeout(2)
            try:
                self.request = conn.recv(8192)
            except OSError:
                return
            if self.reply is None:
                return  # bound, accepted, never answers
            out = record(TYPE_STDOUT, self.reply) + record(
                TYPE_END_REQUEST, b"\x00" * 8
            )
            if self.split_at is None:
                conn.sendall(out)
                return
            conn.sendall(out[: self.split_at])
            conn.sendall(out[self.split_at :])

    def close(self) -> None:
        self.sock.close()


@pytest.fixture
def responder(request):
    server = FakeResponder(*request.param)
    yield server
    server.close()


class TestItAnswersTheReadinessQuestion:
    @pytest.mark.parametrize("responder", [(PONG,)], indirect=True)
    def test_a_pool_that_answers_is_serving(self, responder) -> None:
        assert fastcgi_ping("127.0.0.1", responder.port) is True

    @pytest.mark.parametrize("responder", [(None,)], indirect=True)
    def test_a_socket_that_never_answers_is_not_serving(self, responder) -> None:
        """The exact failure a plain `connect()` check would call healthy."""
        assert fastcgi_ping("127.0.0.1", responder.port, timeout=0.3) is False

    @pytest.mark.parametrize("responder", [(b"Content-Type: text/pl",)], indirect=True)
    def test_headers_cut_off_mid_block_are_not_serving(self, responder) -> None:
        """A child that died mid-response never emitted the blank line."""
        assert fastcgi_ping("127.0.0.1", responder.port) is False

    def test_a_closed_port_is_not_serving(self) -> None:
        with closing(socket.socket()) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        assert fastcgi_ping("127.0.0.1", port, timeout=0.3) is False

    @pytest.mark.parametrize("responder", [(PONG, 12)], indirect=True)
    def test_a_reply_split_across_packets_is_reassembled(self, responder) -> None:
        """Records do not arrive aligned to reads; the parser buffers."""
        assert fastcgi_ping("127.0.0.1", responder.port) is True


class TestTheRequestIsOnePhpFpmUnderstands:
    @pytest.mark.parametrize("responder", [(PONG,)], indirect=True)
    def test_it_asks_for_the_ping_path(self, responder) -> None:
        fastcgi_ping("127.0.0.1", responder.port)
        assert FCGI_PING_PATH.encode() in responder.request

    @pytest.mark.parametrize("responder", [(PONG,)], indirect=True)
    def test_it_sends_begin_params_terminator_and_stdin(self, responder) -> None:
        """php-fpm waits for the empty PARAMS and STDIN records before acting."""
        fastcgi_ping("127.0.0.1", responder.port)
        types = []
        buffer = responder.request
        while len(buffer) >= HEADER.size:
            _, record_type, _, length, padding, _ = HEADER.unpack(buffer[: HEADER.size])
            types.append(record_type)
            buffer = buffer[HEADER.size + length + padding :]
        assert types == [1, 4, 4, 5], "begin, params, end-of-params, end-of-stdin"
