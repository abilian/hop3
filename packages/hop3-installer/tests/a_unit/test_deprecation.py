# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The deprecation-alias mechanism (ADR 052 Migration)."""

from __future__ import annotations

import pytest
from hop3_installer import deprecation
from hop3_installer.deprecation import (
    canonicalize_flags,
    env_bool_with_alias,
    env_with_alias,
    warn_deprecated,
    warn_deprecated_flags,
)

_DEPLOY_ALIASES = {
    "--ssh-user": "--user",
    "--ssh-key": "--identity",
    "--git": "--from git",
    "--local": "--from local",
    "--pypi": "--from pypi",
}


@pytest.fixture(autouse=True)
def _reset_warned():
    deprecation._WARNED.clear()
    yield
    deprecation._WARNED.clear()


def test_warn_deprecated_once_per_name(capsys):
    warn_deprecated("--ssh-key", "--identity")
    warn_deprecated("--ssh-key", "--identity")  # deduped
    err = capsys.readouterr().err
    assert err.count("--ssh-key") == 1
    assert "'--ssh-key' is deprecated" in err
    assert "use '--identity'" in err


def test_warn_deprecated_flags_warns_present(capsys):
    # A store_true source flag (--git) and a same-arg alias (--ssh-key): both
    # present -> both warned, each pointing at the canonical spelling.
    warn_deprecated_flags(["--git", "--host", "h", "--ssh-key", "k"], _DEPLOY_ALIASES)
    err = capsys.readouterr().err
    assert "use '--from git'" in err
    assert "use '--identity'" in err


def test_warn_deprecated_flags_silent_when_absent(capsys):
    # Canonical spelling only -> no notice at all.
    warn_deprecated_flags(["--from", "git", "--identity", "k"], _DEPLOY_ALIASES)
    assert capsys.readouterr().err == ""


def test_warn_deprecated_flags_equals_form(capsys):
    warn_deprecated_flags(["--ssh-user=deploy"], _DEPLOY_ALIASES)
    assert "use '--user'" in capsys.readouterr().err


def test_warn_deprecated_flags_deduped(capsys):
    warn_deprecated_flags(["--git", "--git"], _DEPLOY_ALIASES)
    assert capsys.readouterr().err.count("--git") == 1


def test_env_with_alias_prefers_new(monkeypatch, capsys):
    monkeypatch.setenv("HOP3_VERSION", "1.0")
    monkeypatch.setenv("HOP3_PYPI_VERSION", "0.9")
    assert env_with_alias("HOP3_VERSION", "HOP3_PYPI_VERSION") == "1.0"
    assert capsys.readouterr().err == ""  # new set -> no deprecation notice


def test_env_with_alias_falls_back_and_warns(monkeypatch, capsys):
    monkeypatch.delenv("HOP3_VERSION", raising=False)
    monkeypatch.setenv("HOP3_PYPI_VERSION", "0.9")
    assert env_with_alias("HOP3_VERSION", "HOP3_PYPI_VERSION") == "0.9"
    assert "HOP3_PYPI_VERSION" in capsys.readouterr().err


def test_env_with_alias_default(monkeypatch):
    monkeypatch.delenv("HOP3_VERSION", raising=False)
    monkeypatch.delenv("HOP3_PYPI_VERSION", raising=False)
    assert env_with_alias("HOP3_VERSION", "HOP3_PYPI_VERSION", default="x") == "x"


def test_canonicalize_flags_space_form(capsys):
    argv = ["--ssh-user", "root", "--ssh-key", "/k"]
    out = canonicalize_flags(argv, {"--ssh-user": "--user", "--ssh-key": "--identity"})
    assert out == ["--user", "root", "--identity", "/k"]
    err = capsys.readouterr().err
    assert "--ssh-user" in err
    assert "--ssh-key" in err


def test_canonicalize_flags_equals_form():
    out = canonicalize_flags(["--ssh-user=deploy"], {"--ssh-user": "--user"})
    assert out == ["--user=deploy"]


def test_canonicalize_flags_leaves_values_untouched():
    # A value that coincidentally equals an old flag name must NOT be rewritten
    # (only the flag token is; the following value token passes through).
    out = canonicalize_flags(["--host", "example.com"], {"--ssh-user": "--user"})
    assert out == ["--host", "example.com"]


def test_canonicalize_flags_passthrough():
    argv = ["--docker", "--with", "all"]
    assert canonicalize_flags(argv, {"--ssh-user": "--user"}) == argv


def test_env_bool_with_alias_new_wins(monkeypatch, capsys):
    monkeypatch.setenv("HOP3_CLEAN", "1")
    monkeypatch.setenv("HOP3_FORCE", "1")
    assert env_bool_with_alias("HOP3_CLEAN", "HOP3_FORCE") is True
    assert capsys.readouterr().err == ""  # new set -> no notice


def test_env_bool_with_alias_old_warns(monkeypatch, capsys):
    monkeypatch.delenv("HOP3_CLEAN", raising=False)
    monkeypatch.setenv("HOP3_FORCE", "true")
    assert env_bool_with_alias("HOP3_CLEAN", "HOP3_FORCE") is True
    assert "HOP3_FORCE" in capsys.readouterr().err


def test_env_bool_with_alias_neither_is_false(monkeypatch):
    monkeypatch.delenv("HOP3_CLEAN", raising=False)
    monkeypatch.delenv("HOP3_FORCE", raising=False)
    assert env_bool_with_alias("HOP3_CLEAN", "HOP3_FORCE") is False


def test_env_bool_with_alias_non_truthy_is_false(monkeypatch):
    monkeypatch.setenv("HOP3_CLEAN", "no")
    assert env_bool_with_alias("HOP3_CLEAN", "HOP3_FORCE") is False
