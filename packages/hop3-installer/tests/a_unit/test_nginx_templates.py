# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for nginx template generation.

Focus: server_name shape validation. The templates interpolate the
server_name string directly into nginx config; a malformed value would
corrupt the config file with a confusing error or, in the worst case
under a different trust posture, allow an extra directive to slip in.
The validator runs at the template boundary so callers can't bypass
it accidentally.
"""

from __future__ import annotations

import pytest
from hop3_installer.nginx_templates import (
    generate_full_ssl_config,
    generate_http_only_config,
    generate_https_redirect_config,
    generate_https_server_config,
)


@pytest.mark.parametrize(
    "good_domain",
    [
        "example.com",
        "admin.example.com",
        "deeply.nested.subdomain.example.org",
        "test-1.example.com",
        "abc.co",
        "X1.example.org",  # uppercase / digits in label
    ],
)
def test_http_only_accepts_valid_domains(good_domain):
    out = generate_http_only_config(good_domain)
    assert f"server_name {good_domain};" in out


@pytest.mark.parametrize(
    "bad_domain",
    [
        "",
        " ",
        "no-tld",  # single-label
        "a..b.com",  # empty label
        "-leading-hyphen.example.com",
        "trailing-hyphen-.example.com",
        "evil.com; server_name *.attacker.com",  # injection attempt
        "evil.com\nlisten 8080;",
        "host with space.com",
        "host;rm -rf /",
        "{template}.com",
    ],
)
def test_http_only_rejects_invalid_domains(bad_domain):
    with pytest.raises(ValueError, match="server_name"):
        generate_http_only_config(bad_domain)


def test_http_only_rejects_overlong_domain():
    overlong = ("a" * 60 + ".") * 5  # > 253 chars
    with pytest.raises(ValueError, match="1-253 char"):
        generate_http_only_config(overlong)


def test_https_redirect_validates_too():
    """The HTTPS-redirect block also runs the validator."""
    with pytest.raises(ValueError, match="server_name"):
        generate_https_redirect_config("evil.com; rm -rf /")


def test_https_server_block_validates_too():
    with pytest.raises(ValueError, match="server_name"):
        generate_https_server_config(
            "evil.com\nlisten 9999;",
            ssl_cert="/etc/cert.pem",
            ssl_key="/etc/key.pem",
        )


def test_full_ssl_config_validates_via_subcalls():
    """generate_full_ssl_config calls the redirect+server helpers; both validate."""
    with pytest.raises(ValueError, match="server_name"):
        generate_full_ssl_config(
            "host;evil",
            ssl_cert="/etc/cert.pem",
            ssl_key="/etc/key.pem",
        )


def test_full_ssl_config_accepts_valid():
    out = generate_full_ssl_config(
        "admin.example.com",
        ssl_cert="/etc/cert.pem",
        ssl_key="/etc/key.pem",
    )
    # Both blocks present, both reference the validated name.
    assert "server_name admin.example.com;" in out
    assert "ssl_certificate /etc/cert.pem;" in out


def test_underscore_wildcard_is_accepted():
    """nginx accepts ``_`` as a default-server catch-all; we honour it.

    The installer falls back to ``server_name _;`` when no admin domain
    is configured. Rejecting it would break every install that doesn't
    explicitly set ``admin_domain``.
    """
    out = generate_http_only_config("_")
    assert "server_name _;" in out
    out2 = generate_https_redirect_config("_")
    assert "server_name _;" in out2
    out3 = generate_https_server_config(
        "_", ssl_cert="/etc/cert.pem", ssl_key="/etc/key.pem"
    )
    assert "server_name _;" in out3
