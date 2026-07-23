# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Redeploy must be idempotent: never rotate secrets, never drop operator config.

Regression for a production bug where re-running the server installer (a plain
redeploy) rewrote /home/hop3/hop3-server.toml from a fixed template — wiping
operator-set keys (ACME_*) and minting a NEW postgres superuser password every
time, desyncing the role from every stored credential.
"""

from __future__ import annotations

import stat
import types

import pytest
from hop3_installer.server_installer import installer, postgres, services, verify
from hop3_installer.server_installer.config import ServerInstallerConfig


@pytest.fixture
def home(tmp_path, monkeypatch):
    """
    Point the installer at a throwaway HOME_DIR and stub the ownership calls
    (the real hop3 user / root aren't present in unit tests).
    """
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


def test_managed_secrets_survive_a_redeploy_that_omits_the_flags(home):
    """
    A plain redeploy (no --with mysql/postgres, no --admin-domain) arrives
    with those values as None; they must be REUSED from the existing file, not
    dropped — the MySQL/Postgres service + role still exist on the box.

    Regression for demo28's "MySQL password not configured": a redeploy without
    --with mysql wiped MYSQL_SUPERUSER_PASSWORD while MySQL kept running.
    """
    cfg = home / "hop3-server.toml"
    # First install: --with all.
    verify.write_server_config("pgpw", "mypw", "admin.example.com", secret_key="sk")
    # Plain redeploy: every managed value arrives as None.
    verify.write_server_config(None, None, None, secret_key=None)
    content = cfg.read_text()
    assert 'MYSQL_SUPERUSER_PASSWORD = "mypw"' in content
    assert 'POSTGRES_SUPERUSER_PASSWORD = "pgpw"' in content
    assert 'HOP3_SECRET_KEY = "sk"' in content
    assert 'ADMIN_DOMAIN = "admin.example.com"' in content
    # The MySQL block's companions come back with the reused password.
    assert 'MYSQL_HOST = "127.0.0.1"' in content
    assert 'MYSQL_SUPERUSER = "hop3"' in content


def test_managed_keys_are_not_echoed_into_preserved_block(home):
    """
    Managed keys must not leak into the preserved section and duplicate on
    every redeploy (which would grow the file unboundedly).
    """
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


class TestMissingDbCredentialGate:
    """
    A requested DB left without a TCP-verified superuser credential must
    abort the install, not silently ship a hop3-server.toml the server can't use.
    """

    def test_postgres_without_password_aborts(self):
        cfg = ServerInstallerConfig()  # postgres is the always-on baseline
        err = installer._missing_db_credential_error(cfg, None, "mypw")
        assert err is not None
        assert "PostgreSQL" in err[0]

    def test_mysql_requested_without_password_aborts(self):
        cfg = ServerInstallerConfig(features={"mysql"})
        err = installer._missing_db_credential_error(cfg, "pgpw", None)
        assert err is not None
        assert "MySQL" in err[0]

    def test_mysql_not_requested_is_not_an_error(self):
        # No --with mysql: a None mysql password is expected, not a failure.
        cfg = ServerInstallerConfig()
        assert installer._missing_db_credential_error(cfg, "pgpw", None) is None

    def test_skip_postgres_ignores_missing_pg_password(self):
        cfg = ServerInstallerConfig(skip_postgres=True)
        assert installer._missing_db_credential_error(cfg, None, None) is None

    def test_both_verified_is_not_an_error(self):
        cfg = ServerInstallerConfig(features={"mysql"})
        assert installer._missing_db_credential_error(cfg, "pgpw", "mypw") is None


def test_secret_key_file_roundtrip_and_mode(tmp_path, monkeypatch):
    """
    ADR 048: the signing key persists to the canonical secrets file, 0640,
    and is read back (so a redeploy reuses it rather than rotating).
    """
    monkeypatch.setattr(services, "SECRET_KEY_FILE", tmp_path / "secret-key")
    assert services._read_secret_key_file() is None  # nothing yet
    services._write_secret_key_file("abc123")
    assert services._read_secret_key_file() == "abc123"
    mode = stat.S_IMODE((tmp_path / "secret-key").stat().st_mode)
    assert mode == 0o640


# --- OPERATOR_EMAIL (ADR 056) ---


def test_fresh_install_always_writes_an_operator_email(home):
    """
    Without one, every `[admin].email = "operator"` app fails to deploy, so
    a fresh install must default it (a placeholder is acceptable).
    """
    verify.write_server_config("pgpw", None, None, secret_key="sk")
    content = (home / "hop3-server.toml").read_text()
    assert 'OPERATOR_EMAIL = "admin@example.com"' in content


def test_supplied_operator_email_is_written(home):
    verify.write_server_config(
        "pgpw", None, None, secret_key="sk", operator_email="ops@abilian.com"
    )
    assert (
        'OPERATOR_EMAIL = "ops@abilian.com"' in (home / "hop3-server.toml").read_text()
    )


def test_operator_email_is_reused_on_redeploy(home):
    """
    A redeploy that does not re-pass it must keep the configured value, not
    revert to the placeholder.
    """
    verify.write_server_config(
        "pgpw", None, None, secret_key="sk", operator_email="ops@abilian.com"
    )
    verify.write_server_config("pgpw", None, None, secret_key="sk")  # no email
    content = (home / "hop3-server.toml").read_text()
    assert 'OPERATOR_EMAIL = "ops@abilian.com"' in content
    # and it is not duplicated (managed key, written once)
    assert content.count("OPERATOR_EMAIL = ") == 1
