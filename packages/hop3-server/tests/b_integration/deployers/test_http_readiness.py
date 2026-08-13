# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Deploy readiness must mean *answering HTTP*, not just a bound socket.

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

from hop3.deployers import deployer as dep
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
    """
    A socket that accepts connections but NEVER replies (gunicorn-master-with
    -dead-worker shape): connect() succeeds, the HTTP read times out.
    """
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


# --- redirects: the probe and the test harness must agree ------------------
#
# The harness fetches a `contains` body with `curl -s -L --max-redirs 5`, and
# its own comment says the 3xx body is empty, so for an app whose entry point
# redirects (kanboard → /?controller=AuthController, invoice-ninja → /setup) the
# asserted string lives at the TARGET. This probe followed nothing, so the same
# value copied into `[healthcheck].contains` could never match and the deploy
# failed readiness for an app that served fine.


@pytest.fixture
def routing_server() -> Iterator[tuple[int, dict, list[str]]]:
    """
    A server driven by ``routes[path] = (status, location, body)``.

    Also records the paths it was asked for, so a test can assert how many hops
    the probe actually took rather than only its verdict.
    """
    routes: dict[str, tuple[int, str | None, bytes]] = {}
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            status, location, body = routes.get(self.path, (404, None, b"not found"))
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a: object) -> None:  # silence
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield httpd.server_address[1], routes, seen
    finally:
        httpd.shutdown()
        httpd.server_close()
        t.join(timeout=1)


def test_contains_found_after_following_a_redirect(routing_server) -> None:
    """The kanboard shape: empty 302 at `/`, the asserted content at the target."""
    port, routes, _ = routing_server
    routes["/"] = (302, "/?controller=AuthController", b"")
    routes["/?controller=AuthController"] = (200, None, b"<h1>AuthController</h1>")
    app = SimpleNamespace(port=port, hostname="localhost")

    assert (
        _app_serves_http(app, "/", timeout=2.0, healthcheck_contains="AuthController")
        is True
    )


def test_a_matching_3xx_body_is_not_made_to_take_another_hop(routing_server) -> None:
    """An app that answers on the first hop must not be followed further."""
    port, routes, seen = routing_server
    routes["/"] = (302, "/elsewhere", b"moved to the setup wizard")
    routes["/elsewhere"] = (200, None, b"nothing useful")
    app = SimpleNamespace(port=port, hostname="localhost")

    assert (
        _app_serves_http(app, "/", timeout=2.0, healthcheck_contains="setup wizard")
        is True
    )
    assert seen == ["/"]


def test_an_off_host_redirect_is_not_followed(routing_server) -> None:
    """
    A readiness probe must not chase a redirect off this app.

    Following one would let a deployed app make the server fetch a third party,
    and would report the app healthy on the strength of someone else's page.
    """
    port, routes, seen = routing_server
    routes["/"] = (302, "https://example.com/login", b"")
    app = SimpleNamespace(port=port, hostname="localhost")

    assert (
        _app_serves_http(app, "/", timeout=2.0, healthcheck_contains="anything")
        is False
    )
    assert seen == ["/"]


def test_an_absolute_redirect_to_the_same_app_is_followed(routing_server) -> None:
    port, routes, _ = routing_server
    routes["/"] = (302, "http://localhost/dashboard", b"")
    routes["/dashboard"] = (200, None, b"<title>Dashboard</title>")
    app = SimpleNamespace(port=port, hostname="localhost")

    assert (
        _app_serves_http(app, "/", timeout=2.0, healthcheck_contains="Dashboard")
        is True
    )


def test_a_redirect_loop_terminates(routing_server) -> None:
    port, routes, seen = routing_server
    routes["/a"] = (302, "/b", b"")
    routes["/b"] = (302, "/a", b"")
    app = SimpleNamespace(port=port, hostname="localhost")

    assert (
        _app_serves_http(app, "/a", timeout=2.0, healthcheck_contains="never") is False
    )
    assert len(seen) <= 6, "the hop budget must bound a redirect loop"


def test_without_contains_a_redirect_counts_as_serving_unfollowed(
    routing_server,
) -> None:
    """The status line already answered the question; no hop is needed."""
    port, routes, seen = routing_server
    routes["/"] = (302, "/somewhere", b"")
    app = SimpleNamespace(port=port, hostname="localhost")

    assert _app_serves_http(app, "/", timeout=2.0) is True
    assert seen == ["/"]


def test_a_non_redirect_status_is_answered_on_the_first_hop(routing_server) -> None:
    """isso: `/` is its comment API and answers 400 with a real body."""
    port, routes, seen = routing_server
    routes["/"] = (400, None, b"missing uri query")
    app = SimpleNamespace(port=port, hostname="localhost")

    assert (
        _app_serves_http(
            app, "/", timeout=2.0, healthcheck_contains="missing uri query"
        )
        is True
    )
    assert seen == ["/"]


# --- _wait_for_app_start gate ---------------------------------------------


def test_wait_fails_when_bound_but_not_serving(dead_socket_port: int) -> None:
    """The regression: TCP listening + RUNNING but no HTTP response => NOT ready."""
    app = SimpleNamespace(
        port=dead_socket_port,
        hostname="localhost",
        check_actual_status=lambda: AppStateEnum.RUNNING,
        get_logs=lambda lines=50: [],
    )
    assert _wait_for_app_start(app, timeout=1.0).started is False


def test_wait_succeeds_when_app_answers(http_server: tuple[int, list[int]]) -> None:
    port, _ = http_server
    app = SimpleNamespace(
        port=port,
        hostname="localhost",
        check_actual_status=lambda: AppStateEnum.RUNNING,
        get_logs=lambda lines=50: [],
    )
    assert _wait_for_app_start(app, timeout=3.0).started is True


# --- _update_app_model: port-less (static) deploys skip the worker check ----


def test_static_deploy_clears_stale_port_and_skips_health_check(monkeypatch) -> None:
    """
    A port-less (static) deploy must not be failed by a stale port.

    Regression: `_update_app_model` only *set* app.port (never cleared it), so a
    static redeploy (deployment_info.port is None) kept the previous deploy's
    port (e.g. 48477). `_app_serves_http` then probed that dead port, the wait
    timed out, and the deploy FAILED for a site nginx was already serving — yet
    a plain `hop3 app restart` fixed it. nginx serves static files directly;
    there is no worker to boot, so the worker-boot check must not run.
    """

    waited = {"called": False}
    monkeypatch.setattr(
        dep,
        "_wait_for_app_start",
        lambda *a, **k: (
            waited.__setitem__("called", True) or dep.StartOutcome(started=True)
        ),
    )

    app = SimpleNamespace(
        name="docs",
        runtime="uwsgi",  # stale runtime from a prior (dynamic) deploy
        port=48477,  # stale port from a prior deploy
        hostname=None,
        get_runtime_env=dict,
    )
    deployment_info = SimpleNamespace(port=None, address="site", protocol="static")
    app_config = SimpleNamespace(
        start_timeout=60.0,
        hop3_config=SimpleNamespace(healthcheck_path="", healthcheck_contains=""),
    )

    dep._update_app_model(app, "static", deployment_info, app_config)

    assert app.port == 0, "stale port must be cleared for a port-less deploy"
    assert waited["called"] is False, "static deploy must skip the worker-boot check"


def test_process_deploy_still_runs_health_check(monkeypatch) -> None:
    """A normal (uWSGI/docker) deploy with a real port still gets health-checked."""

    waited = {"called": False}
    monkeypatch.setattr(
        dep,
        "_wait_for_app_start",
        lambda *a, **k: (
            waited.__setitem__("called", True) or dep.StartOutcome(started=True)
        ),
    )

    app = SimpleNamespace(
        name="web",
        runtime="uwsgi",
        port=0,
        hostname=None,
        get_runtime_env=dict,
    )
    deployment_info = SimpleNamespace(port=8080, address="127.0.0.1", protocol="http")
    app_config = SimpleNamespace(
        start_timeout=1.0,
        hop3_config=SimpleNamespace(healthcheck_path="", healthcheck_contains=""),
    )

    dep._update_app_model(app, "uwsgi", deployment_info, app_config)

    assert app.port == 8080
    assert waited["called"] is True, "a real worker port must still be health-checked"
