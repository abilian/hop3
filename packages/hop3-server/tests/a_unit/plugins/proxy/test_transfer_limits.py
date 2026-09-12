# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
[proxy] max-body-size / request-buffering, as each proxy renders them.

The limit an app declares has to reach the vhost, because the proxy refuses an
oversized body before the app can say anything about it: a green deploy that
cannot accept the upload it exists for is the failure shape this section fixes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hop3.core.artifacts import (
    ARTIFACT_FILENAME,
    DEFAULT_MAX_BODY_SIZE,
    BuildArtifact,
    ProxyLimits,
    RuntimeConfig,
    load_proxy_limits,
)
from hop3.core.env import Env
from hop3.orm import App
from hop3.plugins.proxy.caddy._setup import CaddyVirtualHost
from hop3.plugins.proxy.nginx import NginxVirtualHost
from hop3.plugins.proxy.traefik._setup import TraefikVirtualHost, parse_size_to_bytes


@pytest.fixture(autouse=True)
def proxy_dirs():
    for name in ("nginx", "caddy", "traefik", "apps"):
        Path(f"/tmp/hop3/{name}").mkdir(exist_ok=True, parents=True)


def _app(name: str, **limits: object) -> App:
    """An app whose build artifact declares (or omits) [proxy] limits."""
    app = App(name=name)
    app.app_path.mkdir(exist_ok=True, parents=True)
    artifact = BuildArtifact(kind="python", runtime=RuntimeConfig(**limits))
    artifact.save(app.app_path / ARTIFACT_FILENAME)
    return app


def _env() -> Env:
    return Env({
        "HOST_NAME": "testapp.com",
        "BIND_ADDRESS": "127.0.0.1",
        "PORT": "8000",
    })


# --- what the artifact says --------------------------------------------------


def test_limits_default_when_app_has_no_artifact() -> None:
    assert load_proxy_limits(Path("/tmp/hop3/apps/does-not-exist")) == ProxyLimits()


def test_limits_read_from_artifact() -> None:
    app = _app(
        "limits-artifact", proxy_max_body_size="2G", proxy_request_buffering=False
    )
    assert load_proxy_limits(app.app_path) == ProxyLimits("2G", request_buffering=False)


# --- nginx -------------------------------------------------------------------


def _nginx_conf(app: App) -> str:
    nginx = NginxVirtualHost(app, _env(), {"web": "run"})
    nginx.setup_backend()
    nginx.extra_setup()
    return nginx.get_proxy_conf()


def test_nginx_default_body_size() -> None:
    conf = _nginx_conf(_app("nginx-default"))
    assert f"client_max_body_size {DEFAULT_MAX_BODY_SIZE};" in conf
    assert "request_buffering" not in conf


def test_nginx_declared_body_size() -> None:
    conf = _nginx_conf(_app("nginx-big", proxy_max_body_size="2G"))
    assert "client_max_body_size 2G;" in conf
    assert f"client_max_body_size {DEFAULT_MAX_BODY_SIZE};" not in conf


def test_nginx_streams_body_when_buffering_off() -> None:
    """
    A `web` worker is proxied, not uwsgi — so the directive has to arrive as
    `proxy_request_buffering`, which is what the uwsgi→proxy rewrite produces.
    """
    conf = _nginx_conf(_app("nginx-stream", proxy_request_buffering=False))
    assert "proxy_request_buffering off;" in conf
    assert "uwsgi_request_buffering" not in conf


def test_nginx_keeps_uwsgi_spelling_for_wsgi_apps() -> None:
    app = _app("nginx-wsgi", proxy_request_buffering=False)
    nginx = NginxVirtualHost(app, _env(), {"wsgi": "app:app"})
    nginx.setup_backend()
    nginx.extra_setup()
    assert "uwsgi_request_buffering off;" in nginx.get_proxy_conf()


def test_nginx_no_unexpanded_placeholders() -> None:
    """A literal `$HOP3_INTERNAL_…` left in the file is a config nginx rejects."""
    conf = _nginx_conf(_app("nginx-expanded", proxy_max_body_size="1G"))
    assert "$HOP3_INTERNAL_NGINX_MAX_BODY_SIZE" not in conf
    assert "$HOP3_INTERNAL_NGINX_REQUEST_BUFFERING" not in conf


# --- caddy -------------------------------------------------------------------


def test_caddy_renders_declared_body_size() -> None:
    caddy = CaddyVirtualHost(
        _app("caddy-big", proxy_max_body_size="2G"), _env(), {"web": "run"}
    )
    caddy.setup_backend()
    caddy.extra_setup()
    conf = caddy.get_proxy_conf()
    assert "request_body {" in conf
    assert "max_size 2G" in conf


def test_caddy_defaults_to_platform_limit() -> None:
    caddy = CaddyVirtualHost(_app("caddy-default"), _env(), {"web": "run"})
    caddy.setup_backend()
    caddy.extra_setup()
    assert f"max_size {DEFAULT_MAX_BODY_SIZE}" in caddy.get_proxy_conf()


# --- traefik -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ("0", 0),
        ("500", 500),
        ("50m", 52428800),
        ("2G", 2147483648),
        ("1K", 1024),
    ],
)
def test_parse_size_to_bytes(size: str, expected: int) -> None:
    assert parse_size_to_bytes(size) == expected


def test_traefik_renders_body_limit_middleware() -> None:
    traefik = TraefikVirtualHost(
        _app("traefik-big", proxy_max_body_size="2G"), _env(), {"web": "run"}
    )
    traefik.setup_backend()
    traefik.extra_setup()
    conf = traefik.get_proxy_conf()
    assert "traefik-big-body-limit" in conf
    assert "maxRequestBodyBytes: 2147483648" in conf
