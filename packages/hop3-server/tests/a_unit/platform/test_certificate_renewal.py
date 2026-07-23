# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Certificate expiry + renewal decision logic.

Hop3 used to issue a cert once (generate-if-absent) and never renew it, so certs
silently expired. These tests lock the renewal contract: read the real expiry,
know when a cert is due, and re-issue only when needed.
"""

from __future__ import annotations

import datetime
import subprocess

import pytest

from hop3.platform import certificates
from hop3.platform.certificates import Certificate, CertificatesManager


def _make_self_signed(store_dir, domain: str, days: int) -> None:
    """Write a self-signed cert valid for ``days`` into the cert store."""
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            str(days),
            "-subj",
            f"/CN={domain}",
            "-keyout",
            str(store_dir / f"{domain}.key"),
            "-out",
            str(store_dir / f"{domain}.crt"),
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the cert store at a throwaway dir (KEY_STORE is a module global)."""
    monkeypatch.setattr(certificates, "KEY_STORE", tmp_path)
    return tmp_path


def test_not_after_parses_real_cert(store):
    _make_self_signed(store, "a.example.com", 90)
    expiry = Certificate("a.example.com").not_after()
    assert expiry is not None
    delta_days = (expiry - datetime.datetime.now(datetime.UTC)).days
    assert 88 <= delta_days <= 90


def test_days_until_expiry(store):
    _make_self_signed(store, "a.example.com", 90)
    assert 88 <= Certificate("a.example.com").days_until_expiry() <= 90


def test_days_until_expiry_negative_when_expired(store):
    _make_self_signed(store, "a.example.com", 90)
    future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=100)
    assert Certificate("a.example.com").days_until_expiry(now=future) < 0


def test_not_after_none_when_absent(store):
    assert Certificate("missing.example.com").not_after() is None


def test_is_self_signed(store):
    _make_self_signed(store, "a.example.com", 90)
    assert Certificate("a.example.com").is_self_signed() is True


def test_needs_renewal_when_absent(store):
    assert Certificate("missing.example.com").needs_renewal() is True


def test_needs_renewal_respects_threshold(store):
    _make_self_signed(store, "a.example.com", 90)
    cert = Certificate("a.example.com")
    assert cert.needs_renewal(threshold_days=120) is True  # 90 days left < 120
    assert cert.needs_renewal(threshold_days=30) is False  # 90 days left > 30


def test_self_signed_is_renewed_under_certbot(store, monkeypatch):
    # A self-signed cert (a prior fallback) must be replaced when the engine is
    # certbot, even if it's not near expiry.
    _make_self_signed(store, "a.example.com", 90)
    monkeypatch.setattr(certificates, "ACME_ENGINE", "certbot")
    assert Certificate("a.example.com").needs_renewal(threshold_days=30) is True


def test_manager_renew_skips_valid_cert(store, monkeypatch):
    _make_self_signed(store, "a.example.com", 90)
    calls: list[bool] = []
    monkeypatch.setattr(
        Certificate, "generate", lambda self, *, force=False: calls.append(force)
    )
    assert CertificatesManager().renew("a.example.com", threshold_days=30) is False
    assert calls == []  # no re-issue for a still-valid cert


def test_manager_renew_reissues_when_due(store, monkeypatch):
    _make_self_signed(store, "a.example.com", 5)  # expires in 5 days
    calls: list[bool] = []
    monkeypatch.setattr(
        Certificate, "generate", lambda self, *, force=False: calls.append(force)
    )
    assert CertificatesManager().renew("a.example.com", threshold_days=30) is True
    assert calls == [True]  # forced re-issue


def test_manager_renew_force_always_reissues(store, monkeypatch):
    _make_self_signed(store, "a.example.com", 90)  # nowhere near expiry
    calls: list[bool] = []
    monkeypatch.setattr(
        Certificate, "generate", lambda self, *, force=False: calls.append(force)
    )
    assert CertificatesManager().renew("a.example.com", force=True) is True
    assert calls == [True]
