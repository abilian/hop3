# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Per-app cert health model (shared by `hop3 cert status` and the dashboard)."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from hop3.platform import certificates
from hop3.platform.cert_health import cert_health, cert_status


def _make_self_signed(store_dir, domain: str, days: int) -> None:
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:1024",  # test cert only; key size is irrelevant to health rows
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


def _app(name: str, host_name: str):
    return SimpleNamespace(
        name=name, env_vars=[SimpleNamespace(name="HOST_NAME", value=host_name)]
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(certificates, "KEY_STORE", tmp_path)
    return tmp_path


def test_cert_status_classification():
    assert cert_status(None, exists=False) == "missing"
    assert cert_status(None, exists=True) == "missing"
    assert cert_status(-1, exists=True) == "expired"
    assert cert_status(5, exists=True) == "expiring"  # < 14-day warning window
    assert cert_status(30, exists=True) == "ok"


def test_cert_health_rows(store):
    _make_self_signed(store, "a.example.com", 90)
    apps = [
        _app("ok", "a.example.com"),  # healthy self-signed
        _app("catchall", "_"),  # no managed domain -> skipped
        _app("missing", "gone.example.com"),  # domain set, but no cert on disk
    ]

    rows = cert_health(apps)

    assert [r.app_name for r in rows] == ["ok", "missing"]  # catch-all skipped

    ok = rows[0]
    assert ok.domain == "a.example.com"
    assert ok.kind == "self-signed"
    assert ok.status == "ok"
    assert 88 <= ok.days_left <= 90

    missing = rows[1]
    assert missing.kind == "missing"
    assert missing.status == "missing"
    assert missing.days_left is None
