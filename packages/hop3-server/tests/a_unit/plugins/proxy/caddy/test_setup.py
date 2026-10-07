# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
State-based tests for the Caddy proxy config generator.

These exercise the functional core (env -> Caddyfile string) of
``CaddyVirtualHost``, asserting on the produced configuration text. They
deliberately avoid the I/O edges (certificate manager, filesystem writes,
caddy binary, proxy reload), which are framework glue.
"""

from __future__ import annotations

import pytest

from hop3.core.artifacts import ARTIFACT_FILENAME, BuildArtifact, RuntimeConfig
from hop3.core.env import Env
from hop3.core.identifiers import InvalidIdentifierError
from hop3.lib.rootd import RootdError
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
    """
    HOST_NAME values that could escape the `$HOST_NAME {` block are refused
    at setup time, closing the Caddy directive-injection vector. (Whitespace,
    incl. newlines, is treated as a host-list separator and each token is
    validated individually -- see the space-join test.)
    """
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
    assert "https://testapp.com {" in host.get_proxy_conf()


def test_the_client_address_is_left_to_caddy() -> None:
    """Caddy sets X-Forwarded-For; `{remote}` would have sent `ip:port`."""
    conf = make_host({}, workers={"web": "x"}).get_proxy_conf()
    assert "X-Forwarded-For" not in conf
    assert "header_up X-Real-IP {remote_host}" in conf


def test_a_fastcgi_backend_gets_php_fastcgi(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(App, "app_path", property(lambda self: tmp_path))
    BuildArtifact(
        kind="php",
        app_name="testapp",
        runtime=RuntimeConfig(backend_protocol="fastcgi"),
    ).save(tmp_path / ARTIFACT_FILENAME)

    conf = make_host(
        {"PHP_DOCUMENT_ROOT": "/home/hop3/apps/testapp/src/public"},
        workers={"web": "x"},
    ).get_proxy_conf()

    assert "root * /home/hop3/apps/testapp/src/public" in conf
    assert "php_fastcgi 127.0.0.1:8000" in conf
    assert "reverse_proxy" not in conf


# --- HTTPS-only redirect -------------------------------------------------


def test_https_only_emits_http_to_https_redirect() -> None:
    host = make_host({"CADDY_HTTPS_ONLY": "true"}, workers={"web": "x"})
    conf = host.get_proxy_conf()
    assert "http://testapp.com {" in conf
    assert "redir https://{host}{uri} permanent" in conf
    assert "https://testapp.com {" in conf


def test_every_host_gets_both_schemes() -> None:
    conf = make_host({"HOST_NAME": "a.com www.a.com"}, workers={"web": "x"})
    rendered = conf.get_proxy_conf()
    assert "http://a.com, http://www.a.com {" in rendered
    assert "https://a.com, https://www.a.com {" in rendered


def test_the_acme_challenge_is_answered_before_the_redirect() -> None:
    """certbot's HTTP-01 challenge must not be redirected to HTTPS."""
    conf = make_host({}, workers={"web": "x"}).get_proxy_conf()
    http_block = conf.split("https://testapp.com {")[0]
    assert "handle /.well-known/acme-challenge/*" in http_block
    assert http_block.index("acme-challenge") < http_block.index("redir https://")


def test_default_emits_https_redirect() -> None:
    """
    HTTPS-only is the default: an app served on both schemes drops the Secure
    cookies it issues, so logins over plain HTTP fail with a misleading error.
    """
    host = make_host({}, workers={"web": "x"})
    assert "redir https://" in host.get_proxy_conf()


def test_allow_http_serves_plain_http() -> None:
    """[deploy].allow-http = true opts out of the redirect."""
    host = make_host({"HOP3_ALLOW_HTTP": "true"}, workers={"web": "x"})
    conf = host.get_proxy_conf()
    assert "redir https://" not in conf
    # A bare hostname is HTTPS-only to Caddy: port 80 must be named, and in
    # a block of its own, since Caddy refuses `tls` where it listens on HTTP.
    http_block, https_block = conf.split("https://testapp.com {")
    assert "http://testapp.com {" in http_block
    assert "reverse_proxy" in http_block
    assert "reverse_proxy" in https_block


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
    assert "handle_path" not in host.get_proxy_conf()


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


def test_cache_prefixes_set_cache_headers() -> None:
    """The max-age reaches the mapping (an int once crashed it, swallowed)."""
    host = make_host(
        {"CADDY_CACHE_PREFIXES": "/static,/assets", "CADDY_CACHE_CONTROL": "7200"},
        workers={"web": "x"},
    )
    mappings = host.env["HOP3_INTERNAL_CADDY_CACHE_MAPPINGS"]
    assert "path_regexp ^/(static|assets)" in mappings
    assert "max-age=7200" in mappings


def test_reload_proxy_raises_when_all_methods_fail(monkeypatch):
    """A failed caddy reload is fatal (loud), not swallowed."""
    host = CaddyVirtualHost(
        App(name="testapp"), Env({"HOST_NAME": "a.example.com"}), {}
    )

    def _boom(*_a, **_k):
        msg = "no reload method available"
        raise RootdError(msg)

    # The reload now goes through hop3-rootd, not `sudo -n`. Patching the old
    # try_commands would have left this test passing while exercising nothing.
    monkeypatch.setattr(caddy_setup, "reload_service", _boom)
    with pytest.raises(RuntimeError, match="Could not reload caddy"):
        host.reload_proxy()
