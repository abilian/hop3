# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The readiness gate probes each backend in the protocol it actually speaks.

Every backend Hop3 ran spoke HTTP, so the gate required a status line from
the app's own port. php-fpm speaks only FastCGI: point the HTTP probe at it
and all ten catalog PHP apps bind their port, fail the gate, and are reported
as failed deploys while serving correctly through nginx.

See notes/readiness-and-non-http-backends.md.
"""

from __future__ import annotations

import pytest

from hop3.core.artifacts import (
    ARTIFACT_FILENAME,
    BuildArtifact,
    RuntimeConfig,
    load_backend_protocol,
)
from hop3.core.env import Env
from hop3.deployers import deployer as deployer_mod
from hop3.deployers.deployer import _app_serves_http, _name_the_content_mismatch
from hop3.orm import App
from hop3.plugins.proxy._policy import ALLOW_HTTP_KEY


@pytest.fixture
def app(tmp_path, monkeypatch) -> App:
    monkeypatch.setattr(App, "app_path", property(lambda self: tmp_path))
    instance = App(name="testapp")
    instance.port = 8000
    return instance


def write_artifact(app: App, protocol: str) -> None:
    BuildArtifact(
        kind="php",
        app_name=app.name,
        runtime=RuntimeConfig(backend_protocol=protocol),
    ).save(app.app_path / ARTIFACT_FILENAME)


class TestTheProtocolComesFromTheArtifact:
    def test_a_declared_fastcgi_backend_is_named(self, app) -> None:
        write_artifact(app, "fastcgi")
        assert load_backend_protocol(app.app_path) == "fastcgi"

    def test_no_artifact_means_http(self, app) -> None:
        """Everything that predates the field spoke HTTP."""
        assert load_backend_protocol(app.app_path) == "http"

    def test_an_artifact_without_the_field_means_http(self, app) -> None:
        (app.app_path / ARTIFACT_FILENAME).write_text(
            '{"kind": "python", "runtime": {"workers": {"web": "gunicorn app:app"}}}'
        )
        assert load_backend_protocol(app.app_path) == "http"


class TestTheProbeMatchesTheProtocol:
    def test_a_fastcgi_backend_is_pinged_over_fastcgi(self, app, monkeypatch) -> None:
        write_artifact(app, "fastcgi")
        pinged: list[tuple[str, int]] = []
        monkeypatch.setattr(
            deployer_mod,
            "fastcgi_ping",
            lambda host, port, timeout=3.0: pinged.append((host, port)) or True,
        )
        monkeypatch.setattr(
            deployer_mod,
            "_probe_until_content",
            lambda *a, **k: pytest.fail("an HTTP probe would fail on every PHP app"),
        )
        assert _app_serves_http(app, "") is True
        assert pinged == [("127.0.0.1", app.port)]

    def test_an_http_backend_still_gets_the_http_probe(self, app, monkeypatch) -> None:
        write_artifact(app, "http")
        monkeypatch.setattr(
            deployer_mod,
            "fastcgi_ping",
            lambda *a, **k: pytest.fail("no existing app's gate may move"),
        )
        monkeypatch.setattr(deployer_mod, "_probe_until_content", lambda *a, **k: True)
        assert _app_serves_http(app, "") is True

    def test_a_pool_that_does_not_answer_is_not_ready(self, app, monkeypatch) -> None:
        write_artifact(app, "fastcgi")
        monkeypatch.setattr(deployer_mod, "fastcgi_ping", lambda *a, **k: False)
        assert _app_serves_http(app, "") is False

    def test_a_background_worker_is_ready_without_any_probe(
        self, app, monkeypatch
    ) -> None:
        write_artifact(app, "fastcgi")
        app.port = None
        monkeypatch.setattr(
            deployer_mod, "fastcgi_ping", lambda *a, **k: pytest.fail("no port to ping")
        )
        assert _app_serves_http(app, "") is True


class TestAMarkerIsAssertedThroughTheProxy:
    """
    A FastCGI ping proves a worker is alive. It does not prove what the
    application serves, and `[healthcheck].contains` is a claim about a page:
    an install wizard pings exactly as healthily as a finished install. Six
    catalog recipes carry a marker whose comment says it is what proves
    "installed, not sitting on the wizard", so the marker has to be asserted
    somewhere — and for a php-fpm app the only place an HTTP response exists
    is in front of nginx.
    """

    @staticmethod
    def _capture(monkeypatch, result: bool) -> list:
        seen = []
        monkeypatch.setattr(deployer_mod, "fastcgi_ping", lambda *a, **k: True)
        monkeypatch.setattr(
            deployer_mod,
            "_probe_until_content",
            lambda endpoint, path, timeout, contains: (
                seen.append((endpoint, path, contains)) or result
            ),
        )
        return seen

    def test_the_marker_is_checked_over_https_by_default(self, app, monkeypatch):
        write_artifact(app, "fastcgi")
        app.hostname = "shop.example.com"
        monkeypatch.setattr(app, "get_runtime_env", lambda: Env({}))
        seen = self._capture(monkeypatch, True)

        assert _app_serves_http(app, "/admin", healthcheck_contains="Dashboard") is True

        (endpoint, path, contains) = seen[0]
        assert (endpoint.via_proxy, endpoint.tls, endpoint.port) == (True, True, 443)
        assert endpoint.host == "shop.example.com"
        assert (path, contains) == ("/admin", "Dashboard")

    def test_an_app_that_opted_into_plain_http_is_asked_on_port_80(
        self, app, monkeypatch
    ):
        write_artifact(app, "fastcgi")
        monkeypatch.setattr(
            app, "get_runtime_env", lambda: Env({ALLOW_HTTP_KEY: "true"})
        )
        seen = self._capture(monkeypatch, True)

        assert _app_serves_http(app, "/", healthcheck_contains="ok") is True

        endpoint = seen[0][0]
        assert (endpoint.via_proxy, endpoint.tls, endpoint.port) == (True, False, 80)

    def test_a_pool_that_pings_but_serves_the_wrong_page_is_not_ready(
        self, app, monkeypatch
    ):
        """The regression this whole path exists to prevent."""
        write_artifact(app, "fastcgi")
        monkeypatch.setattr(app, "get_runtime_env", lambda: Env({}))
        self._capture(monkeypatch, False)

        assert _app_serves_http(app, "/", healthcheck_contains="Dashboard") is False

    def test_a_dead_pool_is_not_rescued_by_the_proxy(self, app, monkeypatch):
        """
        nginx answers 502 from its own error page when the pool is down, and a
        marker could in principle match it. The pool is the evidence that a
        worker exists, so it is asked first and its "no" is final.
        """
        write_artifact(app, "fastcgi")
        monkeypatch.setattr(app, "get_runtime_env", lambda: Env({}))
        monkeypatch.setattr(deployer_mod, "fastcgi_ping", lambda *a, **k: False)
        monkeypatch.setattr(
            deployer_mod,
            "_probe_until_content",
            lambda *a, **k: pytest.fail(
                "a dead pool is not ready, whatever nginx says"
            ),
        )

        assert _app_serves_http(app, "/", healthcheck_contains="Dashboard") is False

    def test_an_http_app_is_still_asked_on_its_own_port(self, app, monkeypatch):
        """No existing app's gate may move."""
        write_artifact(app, "http")
        app.hostname = "blog.example.com"
        seen = self._capture(monkeypatch, True)

        assert _app_serves_http(app, "/", healthcheck_contains="Welcome") is True

        endpoint = seen[0][0]
        assert (endpoint.via_proxy, endpoint.tls, endpoint.port) == (False, False, 8000)
        assert endpoint.host == "blog.example.com"


class TestTheDiagnosisAsksWhereTheProbeAsked:
    """
    The probe and the failure diagnosis are two readers of one contract. They
    have disagreed twice before — once about the port, once about the probe
    credential — and each time a check passed in one and failed in the other
    within the same minute. For a php-fpm app the diagnosis used to GET the
    app's own port, which speaks FastCGI: no answer, so a serving app was
    reported as "the socket is bound but no worker is serving".
    """

    def test_the_mismatch_is_diagnosed_through_the_proxy(self, app, monkeypatch):
        write_artifact(app, "fastcgi")
        app.hostname = "shop.example.com"
        monkeypatch.setattr(app, "get_runtime_env", lambda: Env({}))
        asked = []
        monkeypatch.setattr(
            deployer_mod,
            "_fetch",
            lambda endpoint, path, timeout, *, want_body: (
                asked.append(endpoint) or (200, "<title>Install Wizard</title>", None)
            ),
        )

        named = _name_the_content_mismatch(app, "/", "Dashboard")

        assert asked[0].via_proxy is True
        assert "the proxy (https://shop.example.com)" in named
        assert "Install Wizard" in named
