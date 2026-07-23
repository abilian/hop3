# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
State-based tests for the generated Traefik config.

These drive the real setup methods (no mocks) and assert on the rendered
YAML buffer returned by `get_proxy_conf()`: router/service/rule for the
host, the backend URL+port, entrypoints, TLS resolver, the no-manual-TLS
default branch, the HTTPS-only redirect branch, and static path handling.
"""

from __future__ import annotations

import pytest

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
    host = TraefikVirtualHost(App(name="testapp"), env, workers or {})
    return host


def rendered(env_overrides: dict | None = None, workers: dict[str, str] | None = None):
    """Drive the real setup pipeline (sans config write/reload) and return YAML."""
    host = make_host(env_overrides or {}, workers)
    host.setup_backend()
    host.setup_certificates()
    host.setup_cache()
    host.setup_static()
    host.extra_setup()
    return host.get_proxy_conf()


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


def test_post_init_uses_first_host_as_primary() -> None:
    host = make_host({"HOST_NAME": "example.com,www.example.com"})
    assert host.env["HOST_NAME"] == "example.com"


# --- backend wiring ------------------------------------------------------


def test_setup_backend_points_service_at_bind_address_and_port() -> None:
    config = rendered({"PORT": "9001", "BIND_ADDRESS": "127.0.0.1"})
    assert 'url: "http://127.0.0.1:9001"' in config


# --- default (auto-HTTPS) config: router/service/rule/entrypoints/tls -----


def test_default_config_emits_router_service_and_host_rule() -> None:
    config = rendered()
    assert "testapp-router:" in config
    assert "testapp-service:" in config
    assert 'rule: "Host(`testapp.com`)"' in config
    assert 'service: "testapp-service"' in config


def test_default_config_listens_on_both_entrypoints_with_cert_resolver() -> None:
    config = rendered()
    assert "- web" in config
    assert "- websecure" in config
    assert "certResolver: hop3" in config


def test_default_config_omits_manual_tls_block() -> None:
    """
    With TRAEFIK_AUTO_HTTPS on (default), no manual `tls.certificates`
    block is appended -- TLS is delegated to Traefik's cert resolver.
    """
    config = rendered()
    assert "certificates:" not in config
    assert "certFile" not in config


def test_default_config_wires_compression_and_headers_middlewares() -> None:
    config = rendered()
    assert "testapp-compression:" in config
    assert "- testapp-compression" in config
    assert "testapp-headers" in config


def test_default_config_blocks_git_folders_by_default() -> None:
    config = rendered()
    assert "testapp-block-git" in config


def test_allow_git_folders_drops_block_git_middleware() -> None:
    config = rendered({"TRAEFIK_ALLOW_GIT_FOLDERS": "1"})
    assert "block-git" not in config


# --- HTTPS-only branch ---------------------------------------------------


def test_https_only_emits_redirect_router_and_https_router() -> None:
    config = rendered({"TRAEFIK_HTTPS_ONLY": "true"})
    assert "testapp-http-router:" in config
    assert "testapp-https-router:" in config
    assert "testapp-https-redirect:" in config
    assert "scheme: https" in config


# --- static path handling ------------------------------------------------
#
# DEFECT (documented current behavior): setup_static() computes the per-path
# routers/services into HOP3_INTERNAL_TRAEFIK_STATIC_ROUTERS/SERVICES, but
# neither TRAEFIK_TEMPLATE nor TRAEFIK_HTTPS_ONLY_TEMPLATE references those
# vars, so static paths never reach the rendered config. These tests pin the
# fix that prevented the int->re.sub crash AND record that the rendered
# routers/services are still dropped, so the day the templates wire them in
# these flip to red. See report.


def test_static_worker_does_not_crash_and_computes_router_env() -> None:
    """
    The static_index int-coercion crash is fixed: setup runs cleanly and
    the static router/service are computed into env (even though the current
    template does not emit them).
    """
    host = make_host({}, workers={"static": "public"})
    host.setup_backend()
    host.setup_certificates()
    host.setup_cache()
    host.setup_static()
    host.extra_setup()

    assert "testapp-static-0:" in host.env["HOP3_INTERNAL_TRAEFIK_STATIC_ROUTERS"]
    assert "PathPrefix(`/`)" in host.env["HOP3_INTERNAL_TRAEFIK_STATIC_ROUTERS"]
    assert "file://" in host.env["HOP3_INTERNAL_TRAEFIK_STATIC_SERVICES"]


def test_static_paths_are_not_emitted_into_rendered_config() -> None:
    """
    DEFECT: computed static routers are absent from the final YAML because
    the main template never references the STATIC_ROUTERS/SERVICES vars.
    """
    config = rendered(workers={"static": "public"})
    assert "testapp-static-0" not in config


# --- cache middleware ----------------------------------------------------
#
# DEFECT (documented current behavior): setup_cache() appends the cache
# middleware to HOP3_INTERNAL_TRAEFIK_CUSTOM_MIDDLEWARES, but the very next
# step in BaseProxy.setup() -- extra_setup() -- resets that var to "",
# wiping the cache middleware before the config is rendered.


def test_cache_control_does_not_crash_and_builds_middleware() -> None:
    """
    The cache_time_control int-coercion crash is fixed: setup_cache runs
    cleanly and renders a cache-headers middleware fragment with the max-age.
    """
    host = make_host({"TRAEFIK_CACHE_CONTROL": "3600"})
    host.setup_cache()

    custom = host.env["HOP3_INTERNAL_TRAEFIK_CUSTOM_MIDDLEWARES"]
    assert "testapp-cache-headers" in custom
    assert "max-age=3600" in custom


def test_cache_middleware_is_wiped_by_extra_setup_before_render() -> None:
    """
    DEFECT: extra_setup() clears CUSTOM_MIDDLEWARES, so the cache headers
    set up by setup_cache() never appear in the rendered config.
    """
    config = rendered({"TRAEFIK_CACHE_CONTROL": "3600"})
    assert "cache-headers" not in config


def test_no_cache_control_omits_cache_headers_middleware() -> None:
    config = rendered()
    assert "cache-headers" not in config
