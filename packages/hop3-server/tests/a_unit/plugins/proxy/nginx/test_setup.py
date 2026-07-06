# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from pathlib import Path

import pytest

from hop3.core.env import Env
from hop3.core.identifiers import InvalidIdentifierError
from hop3.orm import App
from hop3.plugins.proxy.nginx import NginxVirtualHost


@pytest.fixture(autouse=True)
def created_directory():
    Path("/tmp/hop3/nginx/").mkdir(exist_ok=True, parents=True)


def test_get_static_paths_0() -> None:
    env = Env({"HOST_NAME": "testapp.com"})
    workers: dict[str, str] = {}
    nginx = NginxVirtualHost(App(name="testapp"), env, workers)
    assert nginx.get_static_paths() == []


def _backend_env() -> Env:
    return Env({
        "HOST_NAME": "testapp.com",
        "BIND_ADDRESS": "127.0.0.1",
        "PORT": "8000",
    })


def test_setup_backend_proxies_to_app_when_no_waf() -> None:
    nginx = NginxVirtualHost(App(name="testapp"), _backend_env(), {"web": "run"})
    nginx.setup_backend()
    assert (
        nginx.env["HOP3_INTERNAL_NGINX_UWSGI_SETTINGS"]
        == "proxy_pass http://127.0.0.1:8000;"
    )
    assert nginx.env["NGINX_SOCKET"] == "127.0.0.1:8000"


def test_setup_backend_proxies_through_waf_when_enabled() -> None:
    """With a WAF proxy port, nginx targets the proxy, not the app (ADR 050 §7)."""
    app = App(name="testapp")
    app.waf_port = 9123
    nginx = NginxVirtualHost(app, _backend_env(), {"web": "run"})
    nginx.setup_backend()
    assert (
        nginx.env["HOP3_INTERNAL_NGINX_UWSGI_SETTINGS"]
        == "proxy_pass http://127.0.0.1:9123;"
    )
    assert nginx.env["NGINX_SOCKET"] == "127.0.0.1:9123"


@pytest.mark.parametrize(
    "bad_host",
    [
        "example.com;",
        "example.com\nalias /;",
        "example..com",
        "-leading.com",
        "example.com/path",
    ],
)
def test_post_init_rejects_host_name_injection(bad_host: str) -> None:
    """HOST_NAME values that would escape `server_name $HOST_NAME;` are refused
    at proxy setup time, closing the nginx directive-injection critical."""
    env = Env({"HOST_NAME": bad_host})
    with pytest.raises(InvalidIdentifierError):
        NginxVirtualHost(App(name="testapp"), env, {})


def test_post_init_accepts_comma_separated_hosts() -> None:
    env = Env({"HOST_NAME": "example.com,www.example.com"})
    nginx = NginxVirtualHost(App(name="testapp"), env, {})
    # Hosts are space-joined for nginx's server_name directive.
    assert nginx.env["HOST_NAME"] == "example.com www.example.com"


def test_get_static_paths_1() -> None:
    env = Env({
        "HOST_NAME": "testapp.com",
        "NGINX_STATIC_PATHS": "/prefix1:path1",
    })
    workers: dict[str, str] = {}
    nginx = NginxVirtualHost(App(name="testapp"), env, workers)
    result = nginx.get_static_paths()
    assert result[0][0] == "/prefix1"
    assert result[0][1].name == "path1"


def test_get_static_paths_2() -> None:
    env = Env({"HOST_NAME": "testapp.com"})
    workers: dict[str, str] = {"static": "public"}
    nginx = NginxVirtualHost(App(name="testapp"), env, workers)
    result = nginx.get_static_paths()
    assert result[0][0] == "/"
    assert result[0][1].name == "public"


# Copied from hop3-agent/src/hop3/proxies/nginx/setup.py
SAFE_DEFAULTS = Env({
    "NGINX_IPV4_ADDRESS": "0.0.0.0",
    "NGINX_IPV6_ADDRESS": "[::]",
    "BIND_ADDRESS": "127.0.0.1",
})


@pytest.fixture
def env() -> Env:
    env = Env()
    env.update({
        "PORT": "8000",
        "HOST_NAME": "testapp.com",
    })
    env.update(SAFE_DEFAULTS)
    return env


def test_setup_no_workers(env: Env) -> None:
    workers: dict[str, str] = {}
    nginx = NginxVirtualHost(App(name="testapp"), env, workers)
    nginx.setup()


def test_setup_with_workers(env: Env) -> None:
    workers = {"static": "public"}
    nginx = NginxVirtualHost(App(name="testapp"), env, workers)
    nginx.setup()


# --- reload_proxy: hop3-rootd is a hard dependency (ADR 041) -------------
#
# These tests bypass the unit-test reload guard via HOP3_E2E_TEST so the
# rootd path actually runs, then prove that an unreachable / failing daemon
# aborts the deploy loudly instead of silently leaving nginx stale.

from hop3.lib.console import Abort  # noqa: E402
from hop3.lib.rootd import RootdOpError, RootdUnavailableError  # noqa: E402
from hop3.plugins.proxy.nginx import _setup as nginx_setup  # noqa: E402


class _UnavailableClient:
    """Stand-in whose construction fails like a missing daemon socket."""

    def __init__(self, *args, **kwargs) -> None:
        msg = "hop3-rootd socket not found at /run/hop3-rootd/socket"
        raise RootdUnavailableError(msg)


class _OpErrorClient:
    """Stand-in that connects and validates, but errors on reload."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def call(self, op: str, _args: dict) -> dict:
        if op == "nginx.validate_config":
            return {"valid": True}
        code, msg = "kernel_error", "nginx reload exploded"
        raise RootdOpError(code, msg)


def test_reload_proxy_aborts_when_rootd_unavailable(env, monkeypatch) -> None:
    monkeypatch.setenv("HOP3_E2E_TEST", "1")  # bypass the unit-test guard
    monkeypatch.setattr(nginx_setup, "LocalRootdClient", _UnavailableClient)
    nginx = NginxVirtualHost(App(name="testapp"), env, {})
    with pytest.raises(Abort):
        nginx.reload_proxy()


def test_reload_proxy_aborts_when_rootd_reload_errors(env, monkeypatch) -> None:
    monkeypatch.setenv("HOP3_E2E_TEST", "1")
    monkeypatch.setattr(nginx_setup, "LocalRootdClient", _OpErrorClient)
    nginx = NginxVirtualHost(App(name="testapp"), env, {})
    with pytest.raises(Abort):
        nginx.reload_proxy()


@pytest.mark.parametrize(
    ("workers", "expected"),
    [
        ({"static": "public"}, True),
        # Regression: a static site with a build hook must still be static-only;
        # otherwise the upstream block survives with an unallocated port
        # (`upstream 127.0.0.1:0`) and nginx rejects the config.
        ({"prebuild": "build.sh", "static": "public"}, True),
        ({"build": "make", "static": "dist"}, True),
        ({"web": "gunicorn app:app"}, False),
        ({"web": "gunicorn app:app", "static": "public"}, False),
        ({"wsgi": "app:app", "static": "public"}, False),
        ({}, False),
    ],
)
def test_is_static_only(workers: dict[str, str], expected: bool) -> None:
    env = Env({"HOST_NAME": "testapp.com"})
    nginx = NginxVirtualHost(App(name="testapp"), env, workers)
    assert nginx._is_static_only() is expected


def test_static_only_app_with_build_hook_skips_backend() -> None:
    """A static site with a prebuild hook is served directly — never proxied to
    an unallocated port (regression: `upstream 127.0.0.1:0`)."""
    env = Env({"HOST_NAME": "testapp.com"})
    nginx = NginxVirtualHost(
        App(name="testapp"), env, {"prebuild": "x", "static": "public"}
    )
    nginx.setup_backend()
    assert nginx.env.get("HOP3_STATIC_ONLY") == "1"
    assert nginx.env.get("NGINX_SOCKET", "") == ""
