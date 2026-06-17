# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Redeploy must be idempotent: never rotate secrets, never drop operator config.

Regression for a production bug where re-running the server installer (a plain
redeploy) rewrote /home/hop3/hop3-server.toml from a fixed template — wiping
operator-set keys (ACME_*) and minting a NEW postgres superuser password every
time, desyncing the role from every stored credential.
"""

from __future__ import annotations

import types

import pytest
from hop3_installer.server_installer import postgres, verify


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point the installer at a throwaway HOME_DIR and stub the ownership calls
    (the real hop3 user / root aren't present in unit tests)."""
    monkeypatch.setattr(verify, "HOME_DIR", tmp_path)
    monkeypatch.setattr(verify.os, "chown", lambda *a, **k: None)
    monkeypatch.setattr(
        verify.pwd, "getpwnam", lambda _n: types.SimpleNamespace(pw_uid=0)
    )
    monkeypatch.setattr(
        verify.grp, "getgrnam", lambda _n: types.SimpleNamespace(gr_gid=0)
    )
    return tmp_path


def test_read_existing_value_parses_keys_and_handles_absence(home):
    (home / "hop3-server.toml").write_text(
        'POSTGRES_SUPERUSER_PASSWORD = "hop3_abc"\nACME_ENGINE = "certbot"\n'
    )
    assert (
        verify.read_existing_server_config_value("POSTGRES_SUPERUSER_PASSWORD")
        == "hop3_abc"
    )
    assert verify.read_existing_server_config_value("ACME_ENGINE") == "certbot"
    assert verify.read_existing_server_config_value("NOT_THERE") is None


def test_read_existing_value_none_when_file_missing(home):
    assert verify.read_existing_server_config_value("ANYTHING") is None


def test_write_preserves_operator_keys_across_redeploy(home):
    cfg = home / "hop3-server.toml"
    verify.write_server_config("pgpw", None, None, secret_key="sk")
    # Operator enables Let's Encrypt by hand.
    cfg.write_text(
        cfg.read_text() + '\nACME_ENGINE = "certbot"\nACME_EMAIL = "ops@x.io"\n'
    )
    # A redeploy rewrites the file — operator keys must survive.
    verify.write_server_config("pgpw", None, None, secret_key="sk")
    content = cfg.read_text()
    assert 'ACME_ENGINE = "certbot"' in content
    assert 'ACME_EMAIL = "ops@x.io"' in content
    assert 'POSTGRES_SUPERUSER_PASSWORD = "pgpw"' in content


def test_managed_keys_are_not_echoed_into_preserved_block(home):
    """Managed keys must not leak into the preserved section and duplicate on
    every redeploy (which would grow the file unboundedly)."""
    cfg = home / "hop3-server.toml"
    verify.write_server_config("pgpw", "mypw", "admin.example.com", secret_key="sk")
    verify.write_server_config("pgpw", "mypw", "admin.example.com", secret_key="sk")
    content = cfg.read_text()
    for key in (
        "HOP3_SECRET_KEY",
        "POSTGRES_SUPERUSER_PASSWORD",
        "MYSQL_SUPERUSER_PASSWORD",
        "ADMIN_DOMAIN",
    ):
        assert content.count(key) == 1, f"{key} duplicated across redeploy"


def test_set_postgres_password_reuses_existing(monkeypatch):
    """On redeploy the existing superuser password is reused, not rotated."""
    monkeypatch.setattr(
        postgres,
        "run_cmd",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
    )
    pw = postgres._set_postgres_password(existing="hop3_deadbeefcafe")
    assert pw == "hop3_deadbeefcafe"


def test_set_postgres_password_generates_fresh_install(monkeypatch):
    """A fresh install (no existing password) still generates a new one."""
    monkeypatch.setattr(
        postgres,
        "run_cmd",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
    )
    pw = postgres._set_postgres_password(existing=None)
    assert pw is not None
    assert pw.startswith("hop3_")
    assert pw != "hop3_deadbeefcafe"
