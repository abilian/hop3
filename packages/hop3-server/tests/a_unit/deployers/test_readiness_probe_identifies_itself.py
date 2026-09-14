# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
The readiness probe is a client and must say who it is.

``http.client`` sends no User-Agent unless asked, and an anonymous request is
not a neutral one. GoToSocial answers **418 I'm a teapot** to any request
without a User-Agent — a crude bot filter, and a common one. So its
``[healthcheck].contains`` could never match, the readiness gate failed after
60s on every deploy, and the app was blamed: both the native and the Docker
variant failed a catalog run while serving the test harness's ``curl``
perfectly, because curl identifies itself and we did not.

Driven against a real socket that behaves the way GoToSocial does, rather than
by asserting on a header dict: the header has to survive ``http.client``, and
what matters is what the app on the other end sees.
"""

from __future__ import annotations

import socket
import threading
from types import SimpleNamespace

import pytest

from hop3.deployers.deployer import _app_serves_http

#: What GoToSocial serves to a client that does not identify itself, and what
#: it serves to one that does.
_TEAPOT = b"HTTP/1.1 418 I am a teapot\r\nContent-Length: 11\r\n\r\nno user-agent"
_INSTANCE = b'HTTP/1.1 200 OK\r\nContent-Length: 12\r\n\r\n{"uri":"me"}'


class UserAgentSensitiveServer:
    """A one-shot HTTP server that refuses anonymous clients, as gts does."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.seen_user_agents: list[str] = []
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return  # closed by stop()
            with conn:
                request = conn.recv(65536).decode("utf-8", "replace")
                user_agent = _header(request, "user-agent")
                self.seen_user_agents.append(user_agent)
                conn.sendall(_INSTANCE if user_agent else _TEAPOT)

    def stop(self) -> None:
        self.sock.close()


def _header(request: str, name: str) -> str:
    for line in request.split("\r\n")[1:]:
        field, _, value = line.partition(":")
        if field.strip().lower() == name:
            return value.strip()
    return ""


@pytest.fixture
def gts_like():
    server = UserAgentSensitiveServer()
    yield server
    server.stop()


def _app(port: int) -> SimpleNamespace:
    return SimpleNamespace(port=port, hostname="gotosocial.test.local", app_path=None)


@pytest.fixture(autouse=True)
def _http_backend(monkeypatch):
    """The backend protocol is read from the app dir; this app has none."""
    monkeypatch.setattr(
        "hop3.deployers.deployer.load_backend_protocol", lambda _path: "http"
    )


def test_an_app_that_refuses_anonymous_clients_is_still_found_healthy(gts_like):
    assert _app_serves_http(
        _app(gts_like.port), "/api/v1/instance", healthcheck_contains="uri"
    )


def test_the_probe_sends_a_user_agent_naming_hop3(gts_like):
    _app_serves_http(_app(gts_like.port), "/api/v1/instance")
    assert gts_like.seen_user_agents == ["hop3-healthcheck"]
