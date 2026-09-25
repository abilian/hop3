# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A proxy refuses, before writing any config, an app it would serve wrong.

Each proxy declares what it can do (the protocols it speaks to an app's port,
whether it serves files, whether it can front the WAF), and the deploy checks
the app against that. Without the check, Traefik proxied HTTP to a php-fpm
pool, routed static files to a `file://` URL it cannot open, and Caddy and
Traefik both sent a WAF-enabled app's traffic straight past its WAF.
"""

from __future__ import annotations

import pytest

from hop3 import config
from hop3.core.artifacts import ARTIFACT_FILENAME, BuildArtifact, RuntimeConfig
from hop3.core.env import Env
from hop3.deployers.waf import _refuse_unless_proxy_fronts_waf
from hop3.lib.console import Abort
from hop3.orm import App
from hop3.platform import certificates
from hop3.plugins.proxy.caddy import CaddyVirtualHost
from hop3.plugins.proxy.nginx import NginxVirtualHost
from hop3.plugins.proxy.traefik import TraefikVirtualHost


@pytest.fixture
def app(tmp_path, monkeypatch) -> App:
    monkeypatch.setattr(App, "app_path", property(lambda self: tmp_path))
    monkeypatch.setattr(App, "src_path", property(lambda self: tmp_path / "src"))
    return App(name="testapp")


def serving(app: App, protocol: str) -> App:
    BuildArtifact(
        kind="php", app_name=app.name, runtime=RuntimeConfig(backend_protocol=protocol)
    ).save(app.app_path / ARTIFACT_FILENAME)
    return app


def host(proxy, app: App, workers: dict[str, str] | None = None):
    env = Env({
        "APP": app.name,
        "PORT": "8000",
        "HOST_NAME": "testapp.example.org",
        "BIND_ADDRESS": "127.0.0.1",
    })
    return proxy(app, env, workers or {"web": "x"})


def test_traefik_refuses_a_fastcgi_backend(app):
    with pytest.raises(Abort, match="speaks fastcgi, which traefik cannot proxy"):
        host(TraefikVirtualHost, serving(app, "fastcgi")).refuse_unsupported()


@pytest.mark.parametrize("proxy", [NginxVirtualHost, CaddyVirtualHost])
def test_nginx_and_caddy_speak_fastcgi(proxy, app):
    host(proxy, serving(app, "fastcgi")).refuse_unsupported()


@pytest.mark.parametrize(
    "proxy", [NginxVirtualHost, CaddyVirtualHost, TraefikVirtualHost]
)
def test_every_proxy_speaks_http(proxy, app):
    host(proxy, serving(app, "http")).refuse_unsupported()


def test_traefik_refuses_to_serve_files(app):
    with pytest.raises(Abort, match=r"serves files from disk \(/\)"):
        host(TraefikVirtualHost, app, {"static": "public"}).refuse_unsupported()


@pytest.mark.parametrize("proxy", ["caddy", "traefik"])
def test_the_waf_is_refused_on_a_proxy_that_cannot_front_it(proxy, monkeypatch):
    monkeypatch.setattr(config, "HOP3_PROXY_TYPE", proxy)

    with pytest.raises(Abort, match=f"proxy \\({proxy}\\) cannot route"):
        _refuse_unless_proxy_fronts_waf(App(name="testapp"))


def test_nginx_fronts_the_waf(monkeypatch):
    monkeypatch.setattr(config, "HOP3_PROXY_TYPE", "nginx")

    _refuse_unless_proxy_fronts_waf(App(name="testapp"))


@pytest.mark.parametrize(
    ("proxy", "available"), [("nginx", True), ("caddy", False), ("traefik", False)]
)
def test_certbot_is_wired_for_nginx_only(proxy, available, monkeypatch):
    """Issuance writes a temporary nginx vhost; renewal installs into nginx."""
    monkeypatch.setattr(config, "HOP3_PROXY_TYPE", proxy)
    monkeypatch.setattr(certificates, "ACME_EMAIL", "ops@example.org")
    monkeypatch.setattr(certificates.shutil, "which", lambda _name: "/usr/bin/certbot")

    ok, reason = certificates.CertbotEngine().is_available()

    assert ok is available
    if not available:
        assert "through nginx only" in reason
