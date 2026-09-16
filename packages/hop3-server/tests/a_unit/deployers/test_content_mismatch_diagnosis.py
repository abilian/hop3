# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
An app that answers must never be described as an app that does not.

With ``[healthcheck].contains`` the readiness gate wants a body, so an app can
serve every request perfectly and still never be declared ready. The platform
said the opposite: "the server bound its socket but no worker is serving (the
worker failed to boot, or is hung)". invoice-ninja-nix answered 173 probe
requests in the 100 seconds before its deadline — each logged by Laravel, each
in ~0s — and was reported as a socket with nobody behind it, with the one
remedy that cannot help attached: raise the timeout.

Driven against a real socket rather than a stubbed probe: the claim under test
is about what the app on the other end actually served.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from hop3.deployers.deployer import _name_the_start_failure
from hop3.orm import AppStateEnum

#: A 302 whose body names the target, as Laravel's redirect does, and the
#: setup page it points at. Neither carries the literal marker the recipe
#: asked for, which is the whole failure.
_REDIRECT = (
    b"HTTP/1.1 302 Found\r\nLocation: /setup\r\nContent-Length: 30\r\n\r\n"
    b"Redirecting to the setup page."
)
_SETUP = (
    b"HTTP/1.1 200 OK\r\nContent-Length: 44\r\n\r\n"
    b"<title>Invoice Ninja</title><h1>Get started"
)


class Server:
    """A socket that answers every request with ``response``."""

    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return  # closed by stop()
            with conn:
                conn.recv(65536)
                conn.sendall(self.response)

    def stop(self) -> None:
        self.sock.close()


@pytest.fixture
def serving():
    server = Server(_SETUP)
    yield server
    server.stop()


@pytest.fixture
def redirecting():
    server = Server(_REDIRECT)
    yield server
    server.stop()


def _app(port: int) -> SimpleNamespace:
    # No build artifact on this path, so the app speaks HTTP on its own port —
    # which is what these cases are about. The FastCGI variant, whose only HTTP
    # face is nginx's, is covered in test_readiness_backend_protocol.py.
    return SimpleNamespace(
        name="invoice-ninja-nix",
        port=port,
        hostname="invoice-ninja.test.local",
        app_path=Path("/nonexistent/no-artifact"),
    )


def _diagnose(port: int, contains: str, path: str = "/") -> str:
    """The diagnosis for an app whose port is up but whose gate never passed."""
    return _name_the_start_failure(_app(port), AppStateEnum.RUNNING, path, contains)


class TestTheAppAnsweredAndTheMarkerDidNot:
    def test_a_serving_app_is_not_called_a_dead_worker(self, serving):
        assert "no worker is serving" not in _diagnose(serving.port, "/setup")

    def test_it_says_the_app_is_serving(self, serving):
        assert "the app answers on its port" in _diagnose(serving.port, "/setup")

    def test_the_marker_that_did_not_match_is_quoted(self, serving):
        assert "'/setup'" in _diagnose(serving.port, "/setup")

    def test_what_came_back_instead_is_shown(self, serving):
        """Without it the reader has to go and fetch the page themselves."""
        assert "Invoice Ninja" in _diagnose(serving.port, "/setup")

    def test_the_status_it_answered_with_is_named(self, serving):
        assert "returned 200" in _diagnose(serving.port, "/setup")

    def test_the_path_probed_is_named(self, serving):
        assert "/api/health" in _diagnose(serving.port, "x", path="/api/health")

    def test_raising_the_deadline_is_ruled_out(self, serving):
        """The remedy offered for a timeout is the one that cannot work here."""
        assert "a longer deadline cannot help" in _diagnose(serving.port, "/setup")

    def test_a_redirect_whose_target_also_misses_is_still_the_marker(self, redirecting):
        """Every hop answered; none carried the marker."""
        message = _diagnose(redirecting.port, "no-such-marker")
        assert "the app answers on its port" in message
        assert "no worker is serving" not in message

    def test_the_diagnosis_fits_the_column_it_is_stored_in(self, serving):
        assert len(_diagnose(serving.port, "/setup")) <= 1024


class TestWhenTheAppReallyIsSilent:
    def test_a_bound_port_nobody_answers_keeps_the_old_wording(self):
        """
        The original diagnosis is still the right one when it is true: a
        socket bound with no worker behind it. Nothing listens on this port.
        """
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        assert "no worker is serving" in _diagnose(port, "/setup")

    def test_no_marker_means_no_content_diagnosis(self, serving):
        """
        Without `[healthcheck].contains` the gate accepts any status line, so
        reaching the failure path really does mean nothing answered.
        """
        assert "no worker is serving" in _diagnose(serving.port, "")
