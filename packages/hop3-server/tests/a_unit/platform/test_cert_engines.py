# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Cert-engine selection: the public-FQDN gate and the loud-failure contract.

The cert engine is pluggable (self-signed + certbot today). Two invariants this
locks down, both lessons from the edrix.eu outage:

- A non-public name (catch-all "_", a bare app name, a reserved TLD) can only
  ever be self-signed, so it must use the self-signed engine regardless of
  ACME_ENGINE — this is also what keeps the test suite off certbot.
- A *public* domain whose configured engine can't issue must RAISE, never
  silently fall back to an untrusted self-signed cert.
"""

from __future__ import annotations

import pytest

from hop3.platform import certificates
from hop3.platform.certificates import (
    CertbotEngine,
    CertificateError,
    SelfSignedEngine,
    is_public_fqdn,
    select_engine,
)


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("edrix.eu", True),
        ("sub.example.com", True),
        ("a.io", True),
        ("edrix", False),  # bare app name, no dot
        ("_", False),  # catch-all
        ("app.local", False),  # reserved TLD
        ("app.test", False),  # reserved TLD
        ("192.168.0.1", False),  # IP address
        ("*.example.com", False),  # wildcard
        ("edrix.eu\n", False),  # trailing newline rejected (fullmatch, not match)
    ],
)
def test_is_public_fqdn(domain, expected):
    assert is_public_fqdn(domain) is expected


def test_non_public_name_is_self_signed_even_under_certbot(monkeypatch):
    monkeypatch.setattr(certificates, "ACME_ENGINE", "certbot")
    assert isinstance(select_engine("_"), SelfSignedEngine)
    assert isinstance(select_engine("edrix"), SelfSignedEngine)
    assert isinstance(select_engine("app.local"), SelfSignedEngine)


def test_public_fqdn_self_signed_config(monkeypatch):
    monkeypatch.setattr(certificates, "ACME_ENGINE", "self-signed")
    assert isinstance(select_engine("edrix.eu"), SelfSignedEngine)


def test_public_fqdn_certbot_when_available(monkeypatch):
    monkeypatch.setattr(certificates, "ACME_ENGINE", "certbot")
    monkeypatch.setattr(CertbotEngine, "is_available", lambda self: (True, ""))
    assert isinstance(select_engine("edrix.eu"), CertbotEngine)


def test_public_fqdn_certbot_unavailable_raises_loudly(monkeypatch):
    # The core contract: a public domain + an unavailable engine must RAISE,
    # never silently ship a self-signed (untrusted) cert.
    monkeypatch.setattr(certificates, "ACME_ENGINE", "certbot")
    monkeypatch.setattr(
        CertbotEngine, "is_available", lambda self: (False, "certbot is not installed")
    )
    with pytest.raises(CertificateError, match="certbot is not installed"):
        select_engine("edrix.eu")


def test_unknown_engine_raises(monkeypatch):
    monkeypatch.setattr(certificates, "ACME_ENGINE", "vault-acme")
    with pytest.raises(CertificateError, match="Unknown ACME_ENGINE"):
        select_engine("edrix.eu")


def test_certbot_engine_availability(monkeypatch):
    eng = CertbotEngine()

    monkeypatch.setattr(certificates.shutil, "which", lambda _name: None)
    ok, reason = eng.is_available()
    assert ok is False
    assert "certbot" in reason

    monkeypatch.setattr(certificates.shutil, "which", lambda _name: "/usr/bin/certbot")
    monkeypatch.setattr(certificates, "ACME_EMAIL", "")
    ok, reason = eng.is_available()
    assert ok is False
    assert "ACME_EMAIL" in reason

    monkeypatch.setattr(certificates, "ACME_EMAIL", "ops@example.com")
    assert eng.is_available() == (True, "")
