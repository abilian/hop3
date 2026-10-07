# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
The catch backend's sink is real, and its absence is said (ADR 054).

`hop3 server email backend catch` pointed Postfix at 127.0.0.1:1025, where
nothing in the platform listened: the backend reported itself selected, and
every message was deferred, never captured. The sink is now Mailpit (installed
by `--with email`); selecting `catch` checks it answers, and `server email
caught` reads back what it captured.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from hop3.plugins.addons import secrets as secrets_module
from hop3.plugins.email import catcher, server_cli, server_transport as st_module
from hop3.plugins.email.server_cli import ServerEmailCaughtCmd, ServerEmailStatusCmd
from hop3.plugins.email.server_transport import save_server_catch

_MAILPIT_PAGE = {
    "messages": [
        {
            "From": {"Address": "noreply@example.com"},
            "To": None,
            "Bcc": [{"Address": "user@example.com"}],
            "Subject": "Reset your password",
            "Created": "2026-10-04T18:18:56.568Z",
            "Snippet": "Click the link",
        }
    ]
}


@pytest.fixture
def email_root(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets_module, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(st_module, "HOP3_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def smtp_greeter(monkeypatch):
    """A listener that greets like an SMTP server, standing in for Mailpit."""
    server = socket.create_server(("127.0.0.1", 0))

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            with conn:
                conn.sendall(b"220 sink ESMTP ready\r\n")

    threading.Thread(target=serve, daemon=True).start()
    monkeypatch.setattr(catcher, "SINK_SMTP", server.getsockname())
    yield
    server.close()


@pytest.fixture
def mailpit_api(monkeypatch):
    """Mailpit's message-list endpoint, serving one captured message."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(_MAILPIT_PAGE).encode()
            self.send_response(200 if self.path.startswith("/api/v1/messages") else 404)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(catcher, "SINK_HTTP", server.server_address)
    yield
    server.shutdown()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _text(items) -> str:
    return " ".join(json.dumps(it) for it in items)


def test_a_sink_that_greets_answers(smtp_greeter):
    catcher.check_sink_answers()


def test_no_sink_is_said_with_the_way_to_install_it(monkeypatch):
    monkeypatch.setattr(catcher, "SINK_SMTP", ("127.0.0.1", _free_port()))
    with pytest.raises(catcher.CatcherError, match="--with email"):
        catcher.check_sink_answers()


def test_captured_mail_is_read_back(mailpit_api):
    (message,) = catcher.caught_messages()
    assert message.sender == "noreply@example.com"
    assert message.recipients == ("user@example.com",)  # envelope-only: Bcc
    assert message.subject == "Reset your password"


def test_status_names_the_catch_backend_and_its_sink(email_root, smtp_greeter):
    """It said "No server email transport is configured" for catch and direct."""
    save_server_catch("example.com")
    out = _text(ServerEmailStatusCmd().call())
    assert "No server email transport" not in out
    assert "catch" in out
    assert "answering" in out


def test_status_says_when_the_catch_sink_is_down(email_root, monkeypatch):
    save_server_catch("example.com")
    monkeypatch.setattr(catcher, "SINK_SMTP", ("127.0.0.1", _free_port()))
    items = ServerEmailStatusCmd().call()
    assert any(it["t"] == "error" for it in items)


def test_caught_lists_captured_mail(email_root, mailpit_api):
    save_server_catch("example.com")
    out = _text(ServerEmailCaughtCmd().call())
    assert "Reset your password" in out
    assert "user@example.com" in out


def test_caught_refuses_when_the_backend_is_not_catch(email_root, monkeypatch):
    monkeypatch.setattr(
        server_cli, "caught_messages", lambda *_a: pytest.fail("must not query")
    )
    items = ServerEmailCaughtCmd().call()
    assert items[0]["t"] == "error"
    assert "backend catch" in _text(items)
