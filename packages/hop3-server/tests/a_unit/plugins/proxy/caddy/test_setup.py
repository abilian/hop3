# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""State-based tests for the Caddy proxy config generator.

These exercise the functional core (env -> Caddyfile string) of
``CaddyVirtualHost``, asserting on the produced configuration text. They
deliberately avoid the I/O edges (certificate manager, filesystem writes,
caddy binary, proxy reload), which are framework glue.
"""

from __future__ import annotations

import pytest

from hop3.core.env import Env
from hop3.core.identifiers import InvalidIdentifierError
from hop3.lib.util import CommandError
from hop3.orm import App
from hop3.plugins.proxy.caddy import CaddyVirtualHost, _setup as caddy_setup


def make_host(env_overrides: dict, workers: dict[str, str] | None = None):
    """Build a CaddyVirtualHost and run the pure setup steps (no I/O edges)."""
    env = Env({"HOST_NAME": "testapp.com", "PORT": "8000", "APP": "testapp"})
    env.update({"BIND_ADDRESS": "127.0.0.1"})
    env.update(env_overrides)

    host = CaddyVirtualHost(App(name="testapp"), env, workers or {})
    host.setup_backend()
    host.setup_cache()
    host.setup_static()
    host.extra_setup()
    return host


# --- hostname validation (security: directive injection) -----------------


@pytest.mark.parametrize(
    "bad_host",
    [
        "example.com }",
        "example.com{respond 403}",
        "example..com",
        "-leading.com",
        "example.com/path",
    ],
)
def test_post_init_rejects_host_name_injection(bad_host: str) -> None:
    """HOST_NAME values that could escape the `$HOST_NAME {` block are refused
    at setup time, closing the Caddy directive-injection vector. (Whitespace,
    incl. newlines, is treated as a host-list separator and each token is
    validated individually -- see the space-join test.)"""
    env = Env({"HOST_NAME": bad_host, "PORT": "8000", "APP": "testapp"})
    with pytest.raises(InvalidIdentifierError):
        CaddyVirtualHost(App(name="testapp"), env, {})


def test_post_init_space_joins_comma_separated_hosts() -> None:
    env = Env({"HOST_NAME": "example.com,www.example.com", "PORT": "8000"})
    host = CaddyVirtualHost(App(name="testapp"), env, {})
    # Caddy site addresses are space-separated alternative names.
    assert host.env["HOST_NAME"] == "example.com www.example.com"


# --- reverse_proxy block -------------------------------------------------


def test_web_worker_emits_reverse_proxy_to_backend_port() -> None:
    host = make_host({"PORT": "9000"}, workers={"web": "gunicorn app"})
    conf = host.get_proxy_conf()
    assert "reverse_proxy 127.0.0.1:9000" in conf


def test_wsgi_worker_emits_reverse_proxy() -> None:
    host = make_host({}, workers={"wsgi": "app:app"})
    assert "reverse_proxy 127.0.0.1:8000" in host.get_proxy_conf()


def test_no_web_worker_omits_reverse_proxy() -> None:
    """A static-only app (no web/wsgi worker) gets no reverse_proxy block."""
    host = make_host({}, workers={})
    assert "reverse_proxy" not in host.get_proxy_conf()


def test_hostname_opens_the_site_block() -> None:
    host = make_host({}, workers={"web": "x"})
    assert "testapp.com {" in host.get_proxy_conf()


# --- HTTPS-only redirect -------------------------------------------------


def test_https_only_emits_http_to_https_redirect() -> None:
    host = make_host({"CADDY_HTTPS_ONLY": "true"}, workers={"web": "x"})
    conf = host.get_proxy_conf()
    assert "http://testapp.com {" in conf
    assert "redir https://{host}{uri} permanent" in conf
    assert "https://testapp.com {" in conf


def test_default_does_not_emit_https_redirect() -> None:
    host = make_host({}, workers={"web": "x"})
    assert "redir https://" not in host.get_proxy_conf()


# --- TLS (auto-HTTPS branch; manual branch needs the cert manager) -------


def test_auto_https_sets_acme_tls_block() -> None:
    """CADDY_AUTO_HTTPS routes to Caddy's built-in ACME (no cert files)."""
    env = Env({
        "HOST_NAME": "a.com",
        "PORT": "8000",
        "APP": "testapp",
        "CADDY_AUTO_HTTPS": "true",
    })
    host = CaddyVirtualHost(App(name="testapp"), env, {})
    host.setup_certificates()
    assert "tls {" in host.env["HOP3_INTERNAL_CADDY_TLS"]
    assert "email" in host.env["HOP3_INTERNAL_CADDY_TLS"]


# --- static file serving -------------------------------------------------


def test_static_path_emits_file_server_block() -> None:
    host = make_host(
        {"CADDY_STATIC_PATHS": "/assets:/srv/static"}, workers={"web": "x"}
    )
    conf = host.get_proxy_conf()
    assert "handle_path /assets*" in conf
    assert "root * /srv/static" in conf
    assert "file_server" in conf


def test_static_worker_serves_root_path() -> None:
    """A `static` worker maps "/" to the worker's directory."""
    host = make_host({}, workers={"static": "public"})
    conf = host.get_proxy_conf()
    assert "handle_path /*" in conf
    assert "file_server" in conf


def test_no_static_paths_emits_no_file_server() -> None:
    host = make_host({}, workers={"web": "x"})
    assert "file_server" not in host.get_proxy_conf()


# --- compression ---------------------------------------------------------


def test_compression_enabled_by_default() -> None:
    host = make_host({}, workers={"web": "x"})
    assert host.env["HOP3_INTERNAL_CADDY_COMPRESSION"] == "\n    encode gzip zstd\n"


def test_compression_can_be_disabled() -> None:
    host = make_host({"CADDY_DISABLE_COMPRESSION": "true"}, workers={"web": "x"})
    assert host.env["HOP3_INTERNAL_CADDY_COMPRESSION"] == ""


# --- .git folder blocking ------------------------------------------------


def test_git_folder_blocked_by_default() -> None:
    host = make_host({}, workers={"web": "x"})
    conf = host.get_proxy_conf()
    assert "handle /.git*" in conf
    assert "respond 403" in conf


def test_git_folder_serving_can_be_allowed() -> None:
    host = make_host({"CADDY_ALLOW_GIT_FOLDERS": "true"}, workers={"web": "x"})
    assert "handle /.git*" not in host.get_proxy_conf()


# --- caching -------------------------------------------------------------


def test_cache_mappings_empty_without_prefixes() -> None:
    host = make_host({}, workers={"web": "x"})
    assert host.env["HOP3_INTERNAL_CADDY_CACHE_MAPPINGS"] == ""


def test_cache_prefixes_currently_produce_no_mapping() -> None:
    """Locks down a known latent bug: setup_cache feeds an *int*
    max-age into expand_vars, which raises TypeError; the broad except
    swallows it and leaves the cache mappings empty. This test will start
    failing (correctly) once the int->str fix lands -- flag, don't hide."""
    host = make_host(
        {"CADDY_CACHE_PREFIXES": "/static,/assets", "CADDY_CACHE_CONTROL": "7200"},
        workers={"web": "x"},
    )
    assert host.env["HOP3_INTERNAL_CADDY_CACHE_MAPPINGS"] == ""


def test_reload_proxy_raises_when_all_methods_fail(monkeypatch):
    """A failed caddy reload is fatal (loud), not swallowed."""
    host = CaddyVirtualHost(
        App(name="testapp"), Env({"HOST_NAME": "a.example.com"}), {}
    )
    # Bypass the test-environment short-circuit so the reload logic runs.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    def _boom(*_a, **_k):
        raise CommandError(["caddy", "reload"], "no reload method available")

    monkeypatch.setattr(caddy_setup, "try_commands", _boom)
    with pytest.raises(RuntimeError, match="Could not reload caddy"):
        host.reload_proxy()
