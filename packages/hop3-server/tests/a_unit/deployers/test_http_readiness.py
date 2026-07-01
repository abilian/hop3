# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deploy readiness must mean *answering HTTP*, not just a bound socket.

gunicorn (and friends) bind the listen socket in the master before forking
workers, so a plain TCP ``connect()`` succeeds the instant the master is up —
even when the worker is dead/hung and never answers. hop3 used to treat that as
"running" and report a successful deploy behind a dead proxy target. The deploy
gate now additionally requires a real HTTP response.
"""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from hop3.deployers.deployer import _app_serves_http, _wait_for_app_start
from hop3.orm.app import AppStateEnum

if TYPE_CHECKING:
    from collections.abc import Iterator


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def dead_socket_port() -> Iterator[int]:
    """A socket that accepts connections but NEVER replies (gunicorn-master-with
    -dead-worker shape): connect() succeeds, the HTTP read times out."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    port = srv.getsockname()[1]
    held: list[socket.socket] = []
    stop = threading.Event()

    def accept_and_hold() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except OSError:
                continue
            held.append(conn)  # accept, then never send anything

    t = threading.Thread(target=accept_and_hold, daemon=True)
    t.start()
    try:
        yield port
    finally:
        stop.set()
        t.join(timeout=1)
        for c in held:
            c.close()
        srv.close()


@pytest.fixture
def http_server() -> Iterator[tuple[int, list[int]]]:
    """A real HTTP server; status code is taken from ``codes[0]`` per request."""
    codes = [200]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(codes[0])
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a: object) -> None:  # silence
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield httpd.server_address[1], codes
    finally:
        httpd.shutdown()
        httpd.server_close()
        t.join(timeout=1)


# --- _app_serves_http ------------------------------------------------------


def test_bound_but_silent_socket_is_not_serving(dead_socket_port: int) -> None:
    app = SimpleNamespace(port=dead_socket_port, hostname="localhost")
    assert _app_serves_http(app, "", timeout=0.5) is False


def test_live_http_is_serving(http_server: tuple[int, list[int]]) -> None:
    port, _ = http_server
    app = SimpleNamespace(port=port, hostname="localhost")
    assert _app_serves_http(app, "/", timeout=2.0) is True


def test_error_status_still_counts_as_serving(
    http_server: tuple[int, list[int]],
) -> None:
    # A 500 still proves a worker produced a response — the app IS up.
    port, codes = http_server
    codes[0] = 500
    app = SimpleNamespace(port=port, hostname="localhost")
    assert _app_serves_http(app, "/", timeout=2.0) is True


def test_refused_port_is_not_serving() -> None:
    app = SimpleNamespace(port=_free_port(), hostname="localhost")
    assert _app_serves_http(app, "", timeout=0.5) is False


def test_worker_without_port_is_serving() -> None:
    # Background worker: no HTTP endpoint to probe — fall back to True.
    assert _app_serves_http(SimpleNamespace(port=0, hostname=None), "") is True


def test_healthcheck_path_is_normalised(http_server: tuple[int, list[int]]) -> None:
    port, _ = http_server
    app = SimpleNamespace(port=port, hostname="localhost")
    assert _app_serves_http(app, "up", timeout=2.0) is True  # no leading slash


def test_contains_match_counts_as_serving(http_server: tuple[int, list[int]]) -> None:
    # The fixture serves body "ok"; [healthcheck].contains="ok" is satisfied.
    port, _ = http_server
    app = SimpleNamespace(port=port, hostname="localhost")
    assert _app_serves_http(app, "/", timeout=2.0, healthcheck_contains="ok") is True


def test_contains_mismatch_is_not_serving(http_server: tuple[int, list[int]]) -> None:
    # A 200 whose body lacks the required substring is NOT "serving" — the whole
    # point of [healthcheck].contains: a status-only 200 can be the wrong content.
    port, _ = http_server
    app = SimpleNamespace(port=port, hostname="localhost")
    assert _app_serves_http(app, "/", timeout=2.0, healthcheck_contains="nope") is False


# --- _wait_for_app_start gate ---------------------------------------------


def test_wait_fails_when_bound_but_not_serving(dead_socket_port: int) -> None:
    """The regression: TCP listening + RUNNING but no HTTP response => NOT ready."""
    app = SimpleNamespace(
        port=dead_socket_port,
        hostname="localhost",
        check_actual_status=lambda: AppStateEnum.RUNNING,
        get_logs=lambda lines=50: [],
    )
    assert _wait_for_app_start(app, timeout=1.0) is False


def test_wait_succeeds_when_app_answers(http_server: tuple[int, list[int]]) -> None:
    port, _ = http_server
    app = SimpleNamespace(
        port=port,
        hostname="localhost",
        check_actual_status=lambda: AppStateEnum.RUNNING,
        get_logs=lambda lines=50: [],
    )
    assert _wait_for_app_start(app, timeout=3.0) is True
