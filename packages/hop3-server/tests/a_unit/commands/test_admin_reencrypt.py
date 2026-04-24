# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the admin reencrypt-credentials command (Wave 3)."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet

from hop3 import config as c
from hop3.commands.admin import AdminReencryptCredentialsCmd
from hop3.core.credentials import (
    SCHEME_V1_ITERATIONS,
    SCHEME_V1_SALT,
    SCHEME_V2_PREFIX,
    CredentialEncryption,
    _derive_fernet_key,
    reset_credential_encryptor,
)
from hop3.orm import User
from hop3.orm.repositories import AddonCredentialRepository, UserRepository


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    monkeypatch.delenv("HOP3_CREDENTIAL_SALT", raising=False)
    reset_credential_encryptor()
    yield
    reset_credential_encryptor()


@pytest.fixture
def admin_user():
    user = Mock(spec=User)
    user.username = "admin"
    user.is_admin = True
    return user


@pytest.fixture
def mock_user_repo(admin_user):
    repo = Mock(spec=UserRepository)
    repo.get_by_username.return_value = admin_user
    return repo


@pytest.fixture
def mock_nonadmin_user_repo():
    repo = Mock(spec=UserRepository)
    user = Mock(spec=User)
    user.is_admin = False
    repo.get_by_username.return_value = user
    return repo


def _v1_record(secret: str, data: dict) -> str:
    key = _derive_fernet_key(
        secret.encode("utf-8"), SCHEME_V1_SALT, SCHEME_V1_ITERATIONS
    )
    return Fernet(key).encrypt(json.dumps(data).encode("utf-8")).decode("utf-8")


def _make_credential(cid: int, encrypted_data: str) -> Mock:
    cred = Mock()
    cred.id = cid
    cred.app_id = 1
    cred.addon_type = "postgresql"
    cred.addon_name = "db"
    cred.encrypted_data = encrypted_data
    return cred


def test_requires_admin(mock_nonadmin_user_repo):
    cmd = AdminReencryptCredentialsCmd(
        addon_credential_repo=Mock(spec=AddonCredentialRepository),
        user_repo=mock_nonadmin_user_repo,
    )
    result = cmd.call("regular-user")
    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Admin" in result[0]["text"]


def test_requires_authenticated_username():
    # Empty authenticated_username => require_admin returns auth-required error.
    cmd = AdminReencryptCredentialsCmd(
        addon_credential_repo=Mock(spec=AddonCredentialRepository),
        user_repo=Mock(spec=UserRepository),
    )
    result = cmd.call("")
    assert any("Authentication required" in msg.get("text", "") for msg in result)


def test_upgrades_legacy_records(mock_user_repo):
    legacy = _make_credential(1, _v1_record(c.HOP3_SECRET_KEY, {"user": "u"}))
    repo = Mock(spec=AddonCredentialRepository)
    repo.list.return_value = [legacy]
    repo.session = Mock()

    cmd = AdminReencryptCredentialsCmd(
        addon_credential_repo=repo, user_repo=mock_user_repo
    )
    cmd.call("admin")

    # The credential's encrypted_data attribute was rewritten to v2.
    assert legacy.encrypted_data.startswith(SCHEME_V2_PREFIX)
    repo.session.commit.assert_called_once()


def test_skips_records_already_v2(mock_user_repo):
    v2_token = CredentialEncryption().encrypt({"k": "v"})
    original = v2_token
    cred = _make_credential(2, v2_token)
    repo = Mock(spec=AddonCredentialRepository)
    repo.list.return_value = [cred]
    repo.session = Mock()

    cmd = AdminReencryptCredentialsCmd(
        addon_credential_repo=repo, user_repo=mock_user_repo
    )
    cmd.call("admin")

    # Unchanged, no commit needed.
    assert cred.encrypted_data == original
    repo.session.commit.assert_not_called()


def test_dry_run_does_not_mutate(mock_user_repo):
    legacy = _make_credential(3, _v1_record(c.HOP3_SECRET_KEY, {"user": "u"}))
    before = legacy.encrypted_data
    repo = Mock(spec=AddonCredentialRepository)
    repo.list.return_value = [legacy]
    repo.session = Mock()

    cmd = AdminReencryptCredentialsCmd(
        addon_credential_repo=repo, user_repo=mock_user_repo
    )
    result = cmd.call("admin", "--dry-run")

    # Record not rewritten, no commit.
    assert legacy.encrypted_data == before
    repo.session.commit.assert_not_called()
    # And the summary reflects the dry-run framing.
    texts = " ".join(msg.get("text", "") for msg in result)
    assert "would" in texts.lower()


def test_failed_decrypts_are_reported(mock_user_repo):
    # A record that is neither v2-prefixed nor a valid v1 token.
    broken = _make_credential(4, "this-is-garbage")
    repo = Mock(spec=AddonCredentialRepository)
    repo.list.return_value = [broken]
    repo.session = Mock()

    cmd = AdminReencryptCredentialsCmd(
        addon_credential_repo=repo, user_repo=mock_user_repo
    )
    result = cmd.call("admin")

    # Record left untouched.
    assert broken.encrypted_data == "this-is-garbage"
    texts = " ".join(msg.get("text", "") for msg in result)
    assert "Failed to decrypt: 1" in texts
