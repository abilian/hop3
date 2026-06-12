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

from hop3.lib.rootd import RootdUnavailableError
from hop3.platform import certificates
from hop3.platform.certificates import (
    Certificate,
    CertificateError,
    _cert_dns_names,
    verify_cert,
    write_private_key,
)


class _FakeRootdClient:
    """Stub LocalRootdClient context manager recording the ops it's asked to run."""

    calls: list[str] = []  # noqa: RUF012

    def __init__(self, *, fail: Exception | None = None):
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def call(self, op, _args=None):
        if self.fail:
            raise self.fail
        type(self).calls.append(op)
        return {}


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


def test_self_signed_cert_has_san_and_covers_domain(store):
    # The real generate_self_signed (multi-component subject) must produce a cert
    # that satisfies verify_cert. A self-signed cert with no SAN failed to
    # "cover" its own domain on the target's OpenSSL -> every deploy failed.
    cert = Certificate("000-static.test.local")
    cert.generate_self_signed()
    san = subprocess.run(
        [
            "openssl",
            "x509",
            "-noout",
            "-ext",
            "subjectAltName",
            "-in",
            str(cert.crt_file),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "DNS:000-static.test.local" in san  # SAN present, version-independent
    assert cert.covers_domain("000-static.test.local") is True
    verify_cert("000-static.test.local")  # must not raise


def test_cert_dns_names_parses_cn_across_openssl_formats():
    # `openssl x509 -subject` formats the subject differently across versions;
    # all must yield the CN (the bug: only the compact form was parsed).
    for subject in (
        "subject=/C=FR/ST=NA/CN=foo.test.local",  # <3.0 slash form
        "subject=C = FR, ST = NA, CN = foo.test.local",  # 3.0 spaced form
        "subject=CN=foo.test.local",  # compact form
    ):
        assert "foo.test.local" in _cert_dns_names(subject), subject
    # SAN DNS entries are collected too (indented in real output).
    assert "bar.test.local" in _cert_dns_names("    DNS:bar.test.local")


def test_reload_nginx_uses_rootd_not_sudo(monkeypatch):
    # The platform reloads nginx via hop3-rootd, never passwordless sudo (which
    # real servers don't grant). Drop the pytest short-circuit to run the path.
    _FakeRootdClient.calls = []
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(certificates, "LocalRootdClient", _FakeRootdClient)
    certificates.reload_nginx()
    assert _FakeRootdClient.calls == ["nginx.reload"]


def test_reload_nginx_raises_loudly_when_rootd_unavailable(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(
        certificates,
        "LocalRootdClient",
        lambda: _FakeRootdClient(fail=RootdUnavailableError("rootd socket missing")),
    )
    with pytest.raises(CertificateError, match="reload nginx"):
        certificates.reload_nginx()
