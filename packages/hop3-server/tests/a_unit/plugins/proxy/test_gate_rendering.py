# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Each proxy puts a gated app behind hop3-server's check (ADR 062).

What every proxy must render for a gated app, and nothing of it for an open
one: a forward-auth call naming the app, the ``/_hop3/auth/`` route to
hop3-server, and the identity headers and cookies taken from the check's
answer in place of the client's. The e2e suite runs the rendered configs.
"""

from __future__ import annotations

import pytest

from hop3.core.env import Env
from hop3.core.protocols import GATE_REQUEST_HEADERS
from hop3.core.roles import Role
from hop3.lib.console import Abort
from hop3.orm import App
from hop3.plugins.proxy.caddy import CaddyVirtualHost
from hop3.plugins.proxy.nginx import NginxVirtualHost
from hop3.plugins.proxy.traefik import TraefikVirtualHost

NGINX_ENV = {
    "NGINX_SSL": "443 ssl",
    "NGINX_IPV4_ADDRESS": "0.0.0.0",
    "NGINX_IPV6_ADDRESS": "[::]",
}


def host(proxy, *, gated: bool):
    app = App(name="notes")
    app.access_role = Role.VIEWER if gated else None
    env = Env({
        "APP": "notes",
        "PORT": "9000",
        "HOST_NAME": "notes.example.org",
        "BIND_ADDRESS": "127.0.0.1",
        **NGINX_ENV,
    })
    vhost = proxy(app, env, {"web": "x"})
    vhost.setup_backend()
    vhost.setup_cache()
    vhost.setup_static()
    vhost.extra_setup()
    return vhost


def test_nginx_checks_every_request_and_forwards_the_answer():
    conf = host(NginxVirtualHost, gated=True).get_proxy_conf()

    assert "auth_request /_hop3/gate-check;" in conf
    assert "proxy_pass http://127.0.0.1:8000/auth/check;" in conf
    assert "proxy_set_header X-Hop3-App notes;" in conf
    assert "location ^~ /_hop3/auth/ {" in conf
    assert "error_page 401 = @hop3_sign_in;" in conf
    # The state cookie binding a sign-in to its browser rides the redirect.
    assert "auth_request_set $hop3_state $upstream_http_x_hop3_state;" in conf
    assert "add_header Set-Cookie $hop3_state always;" in conf
    app_location = conf[conf.index("location    / {") :]
    for header in (
        "X-Hop3-User $hop3_user",
        "X-Hop3-Role $hop3_role",
        "Cookie $hop3_cookie",
    ):
        assert f"proxy_set_header {header};" in app_location


def test_caddy_checks_every_request_and_replaces_the_headers():
    conf = host(CaddyVirtualHost, gated=True).get_proxy_conf()

    assert "forward_auth @hop3_gated 127.0.0.1:8000 {" in conf
    assert "uri /auth/check?redirect=1" in conf
    assert f"copy_headers {' '.join(GATE_REQUEST_HEADERS)}" in conf
    assert "handle /_hop3/auth/* {" in conf


def test_traefik_checks_every_request_and_replaces_the_headers():
    config = host(TraefikVirtualHost, gated=True).dynamic_config()["http"]

    gate = config["middlewares"]["notes-gate"]["forwardAuth"]
    assert gate["address"] == "http://127.0.0.1:8000/auth/check?redirect=1"
    assert gate["authResponseHeaders"] == list(GATE_REQUEST_HEADERS)
    assert config["routers"]["notes-https"]["middlewares"][:2] == [
        "notes-gate-app",
        "notes-gate",
    ]
    assert config["routers"]["notes-https-hop3"]["service"] == "notes-hop3"


def test_the_underscore_spellings_are_replaced_too():
    """A WSGI server reads X_Hop3_User as X-Hop3-User; a client must not set it."""
    assert {"X_Hop3_User", "X-Hop3_User", "X_Hop3-User"} <= set(GATE_REQUEST_HEADERS)


@pytest.mark.parametrize("proxy", [NginxVirtualHost, CaddyVirtualHost])
def test_an_open_app_has_no_gate(proxy):
    conf = host(proxy, gated=False).get_proxy_conf()

    assert "/_hop3/" not in conf
    assert "hop3_user" not in conf


def test_an_open_app_has_no_gate_on_traefik():
    config = host(TraefikVirtualHost, gated=False).dynamic_config()["http"]

    assert "notes-gate" not in config["middlewares"]
    assert "notes-https-hop3" not in config["routers"]


class TestAnIncludeFileCannotForwardAroundTheGate:
    """
    The gate replaces the identity headers in each location Hop3 writes. A
    location in NGINX_INCLUDE_FILE with its own `proxy_pass` inherits none of
    that, and forwarded the client's own `X-Hop3-User`.
    """

    @staticmethod
    def _vhost(tmp_path, monkeypatch, *, gated: bool, snippet: str):
        src = tmp_path / "src"
        src.mkdir()
        (src / "extra.conf").write_text(snippet)
        monkeypatch.setattr(App, "src_path", property(lambda self: src))
        app = App(name="notes")
        app.access_role = Role.VIEWER if gated else None
        env = Env({
            "APP": "notes",
            "HOST_NAME": "notes.example.org",
            "NGINX_INCLUDE_FILE": "extra.conf",
            **NGINX_ENV,
        })
        return NginxVirtualHost(app, env, {"web": "x"})

    def test_a_forwarding_location_is_refused_on_a_gated_app(
        self, tmp_path, monkeypatch
    ):
        vhost = self._vhost(
            tmp_path,
            monkeypatch,
            gated=True,
            snippet="location /api/ {\n  proxy_pass http://127.0.0.1:9001;\n}\n",
        )

        with pytest.raises(Abort, match="proxy_pass"):
            vhost._refuse_ungated_include()

    def test_a_snippet_that_forwards_nothing_is_fine(self, tmp_path, monkeypatch):
        vhost = self._vhost(
            tmp_path,
            monkeypatch,
            gated=True,
            snippet="client_max_body_size 50m;\n",
        )

        vhost._refuse_ungated_include()

    def test_an_open_app_keeps_its_forwarding_location(self, tmp_path, monkeypatch):
        vhost = self._vhost(
            tmp_path,
            monkeypatch,
            gated=False,
            snippet="location /api/ {\n  proxy_pass http://127.0.0.1:9001;\n}\n",
        )

        vhost._refuse_ungated_include()
