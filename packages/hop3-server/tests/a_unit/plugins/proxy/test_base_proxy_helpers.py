# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
What every proxy shares from ``BaseProxy``: its name, its hosts, its cache
parameters, and that a failed reload fails the deploy.
"""

from __future__ import annotations

import pytest

from hop3.config import HopConfig
from hop3.core.env import Env
from hop3.lib.console import Abort
from hop3.lib.rootd import RootdError
from hop3.orm import App
from hop3.plugins.proxy.caddy import CaddyVirtualHost
from hop3.plugins.proxy.nginx import NginxVirtualHost
from hop3.plugins.proxy.traefik import TraefikVirtualHost, _setup as traefik_setup

PROXIES = [NginxVirtualHost, CaddyVirtualHost, TraefikVirtualHost]


def make(proxy_class, **env: str):
    return proxy_class(
        App(name="testapp"), Env({"HOST_NAME": "a.example.com", **env}), {}
    )


@pytest.mark.parametrize("proxy_class", PROXIES)
def test_every_host_comes_from_host_name_split_on_commas_too(proxy_class) -> None:
    proxy = make(proxy_class, HOST_NAME="a.example.com,b.example.com")
    assert proxy.hosts == ["a.example.com", "b.example.com"]


@pytest.mark.parametrize("proxy_class", PROXIES)
def test_the_name_prefixes_the_proxys_variables(proxy_class) -> None:
    variable = f"{proxy_class.name.upper()}_CACHE_TIME"
    assert make(proxy_class, **{variable: "120"}).cache_param("CACHE_TIME", 5) == 120


@pytest.mark.parametrize("proxy_class", PROXIES)
def test_an_unset_cache_param_is_the_default(proxy_class) -> None:
    assert make(proxy_class).cache_param("CACHE_TIME", 3600) == 3600


@pytest.mark.parametrize("value", ["soon", "-5", "1.5"])
@pytest.mark.parametrize("proxy_class", PROXIES)
def test_an_invalid_cache_param_aborts(proxy_class, value) -> None:
    """It was replaced by the default after a log line nobody reads."""
    variable = f"{proxy_class.name.upper()}_CACHE_TIME"
    with pytest.raises(Abort, match=variable):
        make(proxy_class, **{variable: value}).cache_param("CACHE_TIME", 3600)


def test_caddy_cache_setup_refuses_an_invalid_max_age() -> None:
    proxy = make(
        CaddyVirtualHost, CADDY_CACHE_PREFIXES="/static", CADDY_CACHE_CONTROL="soon"
    )
    proxy.setup_backend()
    with pytest.raises(Abort, match="CADDY_CACHE_CONTROL='soon'"):
        proxy.setup_cache()


def test_a_failed_traefik_reload_fails_the_deploy(monkeypatch) -> None:
    """It printed a warning and the deploy reported success."""

    def _fail(_name):
        msg = "traefik is not under the process manager"
        raise RootdError(msg)

    monkeypatch.setattr(traefik_setup, "reload_service", _fail)
    with pytest.raises(Abort, match="could not reload traefik"):
        make(TraefikVirtualHost).reload_proxy()


@pytest.mark.parametrize("proxy_class", PROXIES)
def test_cache_prefixes_become_an_alternation(proxy_class) -> None:
    variable = f"{proxy_class.name.upper()}_CACHE_PREFIXES"
    proxy = make(proxy_class, **{variable: "/static, media,/assets/img"})
    assert proxy.cache_prefixes() == "static|media|assets/img"


@pytest.mark.parametrize("value", ["/static,", "/a,,/b", "/st atic", "/x)|(.*"])
@pytest.mark.parametrize("proxy_class", PROXIES)
def test_an_invalid_cache_prefix_aborts(proxy_class, value) -> None:
    """nginx logged 'ignoring' and dropped caching; caddy dropped empty items."""
    variable = f"{proxy_class.name.upper()}_CACHE_PREFIXES"
    with pytest.raises(Abort, match=variable):
        make(proxy_class, **{variable: value}).cache_prefixes()


def test_nginx_cache_setup_refuses_a_bad_prefix(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(HopConfig, "_instance", HopConfig(hop3_root=tmp_path))
    proxy = make(NginxVirtualHost, NGINX_CACHE_PREFIXES="/static,")
    with pytest.raises(Abort, match="NGINX_CACHE_PREFIXES='/static,'"):
        proxy.setup_cache()


def test_nginx_cache_setup_refuses_a_missing_cache_path(tmp_path, monkeypatch) -> None:
    """It fell back to the default path after a level-4 log line."""
    monkeypatch.setattr(HopConfig, "_instance", HopConfig(hop3_root=tmp_path))
    proxy = make(
        NginxVirtualHost,
        NGINX_CACHE_PREFIXES="/static",
        NGINX_CACHE_PATH=str(tmp_path / "missing"),
    )
    with pytest.raises(Abort, match="NGINX_CACHE_PATH"):
        proxy.setup_cache()


def test_nginx_cache_setup_renders_the_prefixes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(HopConfig, "_instance", HopConfig(hop3_root=tmp_path))
    proxy = make(NginxVirtualHost, APP="testapp", NGINX_CACHE_PREFIXES="/static,/media")
    proxy.setup_cache()
    mappings = proxy.env["HOP3_INTERNAL_NGINX_CACHE_MAPPINGS"]
    assert "^/(static|media)" in mappings
    assert "uwsgi_cache testapp;" in mappings
    # The zone the mapping uses is the zone the cache path declares.
    cache_path = proxy.env["HOP3_INTERNAL_PROXY_CACHE_PATH"]
    assert f"uwsgi_cache_path {tmp_path / 'cache' / 'testapp'} " in cache_path
    assert "keys_zone=testapp:20m" in cache_path
