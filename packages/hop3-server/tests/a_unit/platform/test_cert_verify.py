# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Post-issue certificate verification (the deploy/renewal post-condition).

verify_cert turns a bad cert into a loud failure instead of quietly serving an
untrusted/expired one — the edrix.eu failure mode. covers_domain backs the
domain-match part (CN + SAN, with single-label wildcards).
"""

from __future__ import annotations

import subprocess

import pytest

from hop3.platform import certificates
from hop3.platform.certificates import (
    Certificate,
    CertificateError,
    verify_cert,
    write_private_key,
)


def _make(store_dir, name: str, *, cn: str, days: int = 90, sans=()):
    args = [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        str(days),
        "-subj",
        f"/CN={cn}",
        "-keyout",
        str(store_dir / f"{name}.key"),
        "-out",
        str(store_dir / f"{name}.crt"),
    ]
    if sans:
        args += ["-addext", "subjectAltName=" + ",".join(f"DNS:{s}" for s in sans)]
    subprocess.run(args, check=True, capture_output=True)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(certificates, "KEY_STORE", tmp_path)
    return tmp_path


def test_covers_domain_cn(store):
    _make(store, "edrix.eu", cn="edrix.eu")
    cert = Certificate("edrix.eu")
    assert cert.covers_domain("edrix.eu") is True
    assert cert.covers_domain("other.com") is False


def test_covers_domain_san(store):
    _make(store, "edrix.eu", cn="edrix.eu", sans=["edrix.eu", "www.edrix.eu"])
    cert = Certificate("edrix.eu")
    assert cert.covers_domain("www.edrix.eu") is True


def test_covers_domain_wildcard(store):
    _make(store, "wild", cn="*.example.com", sans=["*.example.com"])
    cert = Certificate("wild")
    assert cert.covers_domain("a.example.com") is True
    assert cert.covers_domain("a.b.example.com") is False  # one label only
    assert cert.covers_domain("example.com") is False  # not the bare apex


def test_verify_cert_happy(store):
    _make(store, "edrix.eu", cn="edrix.eu")
    verify_cert("edrix.eu")  # must not raise


def test_verify_cert_missing(store):
    with pytest.raises(CertificateError, match="No certificate"):
        verify_cert("absent.example.com")


def test_verify_cert_expired(store, monkeypatch):
    _make(store, "edrix.eu", cn="edrix.eu")
    monkeypatch.setattr(Certificate, "days_until_expiry", lambda self, **_k: -5)
    with pytest.raises(CertificateError, match="expired"):
        verify_cert("edrix.eu")


def test_verify_cert_wrong_domain(store):
    # Cert filed under edrix.eu but issued for someone else -> does not cover.
    _make(store, "edrix.eu", cn="elsewhere.example.com")
    with pytest.raises(CertificateError, match="does not cover"):
        verify_cert("edrix.eu")


def test_verify_cert_self_signed_under_certbot(store, monkeypatch):
    _make(store, "edrix.eu", cn="edrix.eu")  # self-signed
    monkeypatch.setattr(certificates, "ACME_ENGINE", "certbot")
    with pytest.raises(CertificateError, match="self-signed"):
        verify_cert("edrix.eu")


def test_write_private_key_is_owner_only(tmp_path):
    key = tmp_path / "x.key"
    write_private_key(key, "SECRET")
    assert key.read_text() == "SECRET"
    assert (key.stat().st_mode & 0o777) == 0o600


def test_self_signed_key_is_owner_only(store):
    cert = Certificate("perm.example.com")
    cert.generate_self_signed()
    assert (cert.key_file.stat().st_mode & 0o777) == 0o600
