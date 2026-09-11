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
from hop3.deployers import deployer as deployer_mod
from hop3.deployers.deployer import _app_serves_http
from hop3.orm import App


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
