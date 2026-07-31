# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The shared HTTP -> HTTPS redirect policy (every proxy plugin).

Regression: apps were served on both HTTP and HTTPS. An app told it lives at an
https:// URL issues Secure session/CSRF cookies, which a browser will not send
back over plain HTTP — so logging in over HTTP failed with "credentials do not
match", blaming the password rather than the scheme. Forgejo and Bugsink both
presented this way.
"""

from __future__ import annotations

import pytest

from hop3.core.env import Env
from hop3.plugins.proxy._policy import ALLOW_HTTP_KEY, should_redirect_to_https
from hop3.plugins.proxy.nginx._templates import NGINX_HTTPS_ONLY_TEMPLATE

LEGACY_KEYS = ["NGINX_HTTPS_ONLY", "CADDY_HTTPS_ONLY", "TRAEFIK_HTTPS_ONLY"]


@pytest.mark.parametrize("legacy_key", LEGACY_KEYS)
def test_redirect_is_the_default(legacy_key):
    """An app that declares nothing gets the redirect."""
    assert should_redirect_to_https(Env({}), legacy_key) is True


@pytest.mark.parametrize("legacy_key", LEGACY_KEYS)
def test_allow_http_opts_out(legacy_key):
    """[deploy].allow-http = true reaches every proxy through one flag."""
    env = Env({ALLOW_HTTP_KEY: "true"})
    assert should_redirect_to_https(env, legacy_key) is False


@pytest.mark.parametrize("legacy_key", LEGACY_KEYS)
def test_allow_http_false_keeps_the_redirect(legacy_key):
    """Dropping allow-http from a recipe restores the redirect."""
    env = Env({ALLOW_HTTP_KEY: "false"})
    assert should_redirect_to_https(env, legacy_key) is True


@pytest.mark.parametrize("legacy_key", LEGACY_KEYS)
def test_explicit_legacy_var_still_wins(legacy_key):
    """
    An operator who set <PROXY>_HTTPS_ONLY before this default keeps it.

    Both directions: the per-app override is the escape hatch, so it must be
    able to force HTTP-serving on as well as off.
    """
    assert should_redirect_to_https(Env({legacy_key: "false"}), legacy_key) is False
    assert should_redirect_to_https(Env({legacy_key: "true"}), legacy_key) is True

    # ...and it beats the recipe-level flag, whichever way they disagree.
    env = Env({ALLOW_HTTP_KEY: "true", legacy_key: "true"})
    assert should_redirect_to_https(env, legacy_key) is True


def test_default_template_redirects_and_exempts_acme():
    """
    The redirect must not break ACME: the challenge path stays on HTTP.

    Redirecting /.well-known/acme-challenge to HTTPS would break issuance and
    renewal on a host that has no valid cert yet — the exact moment it is needed.
    """
    assert "return 301 https://$server_name$request_uri;" in NGINX_HTTPS_ONLY_TEMPLATE
    acme_at = NGINX_HTTPS_ONLY_TEMPLATE.index("/.well-known/acme-challenge")
    redirect_at = NGINX_HTTPS_ONLY_TEMPLATE.index("return 301")
    assert acme_at < redirect_at, "ACME location must precede the catch-all redirect"
