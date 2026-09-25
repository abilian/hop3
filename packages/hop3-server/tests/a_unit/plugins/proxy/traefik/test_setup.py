# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
State-based tests for the generated Traefik config.

These drive the real setup methods (no mocks) and assert on the dynamic
configuration the plugin writes, parsed back from its YAML: one router per
scheme, the host rule, the backend, the redirect, the certificate, the
middleware chain and the `.git` refusal.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from hop3.core.env import Env
from hop3.core.identifiers import InvalidIdentifierError
from hop3.orm import App
from hop3.plugins.proxy.traefik import TraefikVirtualHost


def make_host(env_overrides: dict, workers: dict[str, str] | None = None):
    # `APP` is seeded into the env by the deployer's make_env() (run/spawn.py)
    # before the proxy is constructed; mirror that so `$APP` substitutes.
    env = Env({
        "APP": "testapp",
        "PORT": "8000",
        "HOST_NAME": "testapp.com",
        "BIND_ADDRESS": "127.0.0.1",
    })
    env.update(env_overrides)
    return TraefikVirtualHost(App(name="testapp"), env, workers or {})


def rendered(env_overrides: dict | None = None) -> dict[str, Any]:
    """Drive the setup pipeline (sans certificate, write and reload), parsed."""
    host = make_host(env_overrides or {})
    host.setup_backend()
    host.setup_cache()
    host.setup_static()
    host.extra_setup()
    return yaml.safe_load(host.get_proxy_conf())


def routers(config: dict[str, Any]) -> dict[str, Any]:
    return config["http"]["routers"]


# --- host validation (security boundary) ---------------------------------


@pytest.mark.parametrize(
    "bad_host",
    ["example.com\nrule: bad", "example..com", "-leading.com", "example.com/path"],
)
def test_post_init_rejects_host_name_injection(bad_host: str) -> None:
    """
    HOST_NAME values that would escape the Host(`...`) rule are refused at
    setup time, closing the Traefik config-injection critical.
    """
    with pytest.raises(InvalidIdentifierError):
        make_host({"HOST_NAME": bad_host})


def test_every_host_is_routed() -> None:
    """Only the first host used to be; the others got no route at all."""
    config = rendered({"HOST_NAME": "example.com,www.example.com"})
    rule = routers(config)["testapp-https"]["rule"]
    assert rule == "Host(`example.com`) || Host(`www.example.com`)"


# --- backend wiring ------------------------------------------------------


def test_the_service_points_at_the_app_port() -> None:
    config = rendered({"PORT": "9001"})
    service = config["http"]["services"]["testapp-service"]
    assert service == {"loadBalancer": {"servers": [{"url": "http://127.0.0.1:9001"}]}}


# --- one router per scheme -----------------------------------------------


def test_https_is_served_with_the_hop3_certificate() -> None:
    config = rendered()
    https = routers(config)["testapp-https"]
    assert https["entryPoints"] == ["websecure"]
    assert https["tls"] == {}
    [cert] = config["tls"]["certificates"]
    assert cert["certFile"].endswith("/testapp.crt")
    assert cert["keyFile"].endswith("/testapp.key")


def test_no_router_names_a_certificate_resolver() -> None:
    """`certResolver: hop3` named a resolver nothing defined."""
    assert "certResolver" not in yaml.safe_dump(rendered())


def test_default_config_redirects_http_to_https() -> None:
    """
    HTTPS-only is the default: an app served on both schemes drops the Secure
    cookies it issues, so logins over plain HTTP fail with a misleading error.
    """
    config = rendered()
    http = routers(config)["testapp-http"]
    assert http["entryPoints"] == ["web"]
    assert "tls" not in http
    assert http["middlewares"] == ["testapp-https-redirect"]
    redirect = config["http"]["middlewares"]["testapp-https-redirect"]
    assert redirect == {"redirectScheme": {"scheme": "https", "permanent": True}}


def test_allow_http_serves_the_app_on_port_80() -> None:
    """A router with `tls` matches only HTTPS: plain HTTP needs its own."""
    config = rendered({"HOP3_ALLOW_HTTP": "true"})
    http = routers(config)["testapp-http"]
    assert "tls" not in http
    assert http["service"] == "testapp-service"
    assert "testapp-https-redirect" not in http["middlewares"]
    assert "testapp-https-redirect" not in config["http"]["middlewares"]


def test_both_schemes_share_the_middleware_chain() -> None:
    config = rendered({"HOP3_ALLOW_HTTP": "true"})
    chain = ["testapp-compression", "testapp-body-limit"]
    assert routers(config)["testapp-http"]["middlewares"] == chain
    assert routers(config)["testapp-https"]["middlewares"] == chain


# --- .git ----------------------------------------------------------------


def test_git_folders_are_refused_on_both_schemes() -> None:
    config = rendered()
    for name in ("testapp-http-git", "testapp-https-git"):
        router = routers(config)[name]
        assert router["rule"] == "(Host(`testapp.com`)) && PathPrefix(`/.git`)"
        assert router["middlewares"] == ["testapp-deny"]
    deny = config["http"]["middlewares"]["testapp-deny"]
    assert deny == {"ipAllowList": {"sourceRange": ["255.255.255.255/32"]}}


def test_allow_git_folders_drops_the_refusal() -> None:
    config = rendered({"TRAEFIK_ALLOW_GIT_FOLDERS": "1"})
    assert "testapp-http-git" not in routers(config)
    assert "testapp-deny" not in config["http"]["middlewares"]


# --- cache headers -------------------------------------------------------


def test_cache_control_adds_cache_headers_to_the_chain() -> None:
    """They used to be built, then wiped before the config was rendered."""
    config = rendered({"TRAEFIK_CACHE_CONTROL": "3600"})
    assert "testapp-cache-headers" in routers(config)["testapp-https"]["middlewares"]
    headers = config["http"]["middlewares"]["testapp-cache-headers"]["headers"]
    assert headers["customResponseHeaders"]["Cache-Control"] == "public, max-age=3600"


def test_no_cache_control_omits_cache_headers() -> None:
    assert "testapp-cache-headers" not in rendered()["http"]["middlewares"]
