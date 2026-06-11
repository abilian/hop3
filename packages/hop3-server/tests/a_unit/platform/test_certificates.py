# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the certificate domain validator and path derivation.

These lock down the pure logic in ``hop3.platform.certificates``:
the FQDN regex (what certbot will accept) and how a ``Certificate``
derives its on-disk ``.key`` / ``.crt`` paths from a domain name.
"""

from __future__ import annotations

import pytest

from hop3.platform.certificates import (
    KEY_STORE,
    RE_DOMAIN_VALIDATOR,
    Certificate,
)


def _matches(domain: str) -> bool:
    """True if the domain is accepted by the FQDN validator."""
    return RE_DOMAIN_VALIDATOR.match(domain) is not None


# --- Domain validator: accepted (valid FQDNs) --------------------------------


@pytest.mark.parametrize(
    "domain",
    [
        "example.com",
        "sub.example.com",
        "sub-domain.example.com",
        "a.b.c.example.com",
        "a.io",  # 2-char TLD is the minimum
        # Numeric-leading labels with hyphens (real deploy hostname).
        # Previously a FIXME; the validator now accepts it.
        "010-flask-pip-wsgi-1742306604.hop-dev.abilian.com",
        # Punycode (IDN) hostnames are plain a-z0-9/hyphen, so they pass.
        "xn--80ak6aa92e.com",
    ],
)
def test_validator_accepts_valid_fqdn(domain: str):
    """Well-formed multi-level FQDNs are accepted."""
    assert _matches(domain)


# --- Domain validator: rejected ----------------------------------------------


@pytest.mark.parametrize(
    "domain",
    [
        "",  # empty
        "example",  # no TLD
        "example.c",  # 1-char TLD (needs >= 2)
        "localhost",  # bare hostname, no dot
        "example..com",  # consecutive dots
        "-example.com",  # leading hyphen
        "example-.com",  # label ends with hyphen
        ".example.com",  # leading dot
        "example.com.",  # trailing dot
        "ex_ample.com",  # underscore not allowed
        "exa mple.com",  # whitespace not allowed
        "*.example.com",  # wildcard not allowed
        "*.com",  # wildcard not allowed
        "192.168.0.1",  # IPv4 (numeric TLD fails [a-z]{2,})
        "127.0.0.1",  # IPv4
    ],
)
def test_validator_rejects_malformed_domain(domain: str):
    """Malformed inputs, wildcards, and IP addresses are rejected."""
    assert not _matches(domain)


def test_validator_is_case_sensitive_lowercase_only():
    """The validator only matches lowercase; callers must lowercase first.

    ``is_public_fqdn`` relies on this by matching ``domain_name.lower()``
    rather than the raw value.
    """
    assert not _matches("EXAMPLE.COM")
    assert not _matches("Example.com")
    assert _matches("example.com")


def test_validator_accepts_reserved_tld_shape():
    """Reserved TLDs are syntactically valid FQDNs.

    The regex only checks shape; rejecting .local/.test/.localhost is a
    separate concern handled by the reserved-TLD set in certbot generation.
    """
    assert _matches("example.local")
    assert _matches("example.test")
    assert _matches("app.localhost")


# --- Certificate path / naming derivation ------------------------------------


def test_certificate_paths_derive_from_domain_and_key_store():
    """key_file / crt_file live in KEY_STORE, named <domain>.key / .crt."""
    cert = Certificate(domain_name="example.com")

    assert cert.key_file == KEY_STORE / "example.com.key"
    assert cert.crt_file == KEY_STORE / "example.com.crt"


def test_certificate_paths_share_stem_differ_by_suffix():
    """The two artifacts share a stem and differ only by extension."""
    cert = Certificate(domain_name="sub.example.com")

    assert cert.key_file.suffix == ".key"
    assert cert.crt_file.suffix == ".crt"
    assert cert.key_file.with_suffix("") == cert.crt_file.with_suffix("")
    assert cert.key_file.parent == cert.crt_file.parent == KEY_STORE


def test_certificate_is_value_object_equal_by_domain():
    """Certificate is a frozen value object: equal iff same domain_name."""
    assert Certificate(domain_name="example.com") == Certificate(
        domain_name="example.com"
    )
    assert Certificate(domain_name="a.com") != Certificate(domain_name="b.com")
