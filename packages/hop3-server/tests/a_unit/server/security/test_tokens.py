# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for JWT token generation and validation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from hop3.server.security.tokens import (
    MAGIC_LINK_EXPIRY_MINUTES,
    MAGIC_LINK_SCOPE,
    create_magic_token,
    create_token,
    generate_api_key,
    get_secret_key,
    validate_magic_token,
    validate_token,
)


@pytest.fixture(autouse=True)
def setup_secret_key(monkeypatch, tmp_path):
    """Provide a test signing key via the env, and neutralize the canonical
    file. ADR 048 reads /etc/hop3/secret-key first; pointing it at an absent
    path keeps these env-based tests deterministic regardless of host (e.g. a
    dev machine that is also a provisioned server)."""
    monkeypatch.setattr(
        "hop3.server.security.tokens.SECRET_KEY_FILE", tmp_path / "no-secret-key"
    )
    os.environ["HOP3_SECRET_KEY"] = "test-secret-key-for-testing-only"
    yield
    os.environ.pop("HOP3_SECRET_KEY", None)


def test_secret_key_file_takes_precedence(monkeypatch, tmp_path):
    """The canonical secrets-tier file wins over env and config (one source)."""
    key_file = tmp_path / "secret-key"
    key_file.write_text("file-key\n")
    monkeypatch.setattr("hop3.server.security.tokens.SECRET_KEY_FILE", key_file)
    monkeypatch.setenv("HOP3_SECRET_KEY", "env-key")
    assert get_secret_key() == "file-key"


def test_secret_key_falls_back_to_env_when_file_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "hop3.server.security.tokens.SECRET_KEY_FILE", tmp_path / "absent"
    )
    monkeypatch.setenv("HOP3_SECRET_KEY", "env-key")
    assert get_secret_key() == "env-key"


def test_secret_key_falls_back_to_config_when_file_and_env_absent(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "hop3.server.security.tokens.SECRET_KEY_FILE", tmp_path / "absent"
    )
    monkeypatch.delenv("HOP3_SECRET_KEY", raising=False)
    monkeypatch.setattr("hop3.config.HOP3_SECRET_KEY", "toml-key")
    assert get_secret_key() == "toml-key"


def test_create_token_basic():
    """Test basic token creation."""
    token = create_token("testuser")
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_token_with_scopes():
    """Test token creation with custom scopes."""
    token = create_token("testuser", scopes=["admin", "user"])
    user_info = validate_token(token)

    assert user_info is not None
    assert user_info["username"] == "testuser"
    assert "admin" in user_info["scopes"]
    assert "user" in user_info["scopes"]


def test_create_token_with_custom_expiry():
    """Test token creation with custom expiration time."""
    token = create_token("testuser", expires_hours=1)
    user_info = validate_token(token)

    assert user_info is not None
    # Check that expiration is roughly 1 hour from now
    expires_at = user_info["expires_at"]
    expected_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    # Allow 10 second tolerance
    assert abs(expires_at - expected_expiry.timestamp()) < 10


def test_validate_token_success():
    """Test successful token validation."""
    token = create_token("testuser", scopes=["authenticated"])
    user_info = validate_token(token)

    assert user_info is not None
    assert user_info["username"] == "testuser"
    assert user_info["scopes"] == ["authenticated"]
    assert "issued_at" in user_info
    assert "expires_at" in user_info
    assert "token_id" in user_info


def test_validate_token_invalid():
    """Test validation of invalid token."""
    invalid_token = "not.a.valid.token"
    user_info = validate_token(invalid_token)

    assert user_info is None


def test_validate_token_wrong_secret():
    """Test validation of token signed with different secret."""
    # Create token with one secret
    token = create_token("testuser")

    # Try to validate with different secret
    os.environ["HOP3_SECRET_KEY"] = "different-secret-key-for-testing"
    user_info = validate_token(token)

    assert user_info is None


def test_validate_token_expired():
    """Test validation of expired token."""
    # Create a token that expires immediately
    token = create_token("testuser", expires_hours=-1)  # Already expired

    user_info = validate_token(token)
    assert user_info is None


def test_generate_api_key():
    """Test API key generation."""
    key1 = generate_api_key()
    key2 = generate_api_key()

    assert isinstance(key1, str)
    assert isinstance(key2, str)
    assert len(key1) > 0
    assert len(key2) > 0
    # Keys should be different
    assert key1 != key2


def test_token_contains_jti():
    """Test that tokens contain a unique JWT ID."""
    token1 = create_token("user1")
    token2 = create_token("user1")

    info1 = validate_token(token1)
    info2 = validate_token(token2)

    assert info1 is not None
    assert info2 is not None
    assert info1["token_id"] != info2["token_id"]


def test_create_token_without_secret_key(monkeypatch):
    """Token creation fails when no secret is configured (env AND config).

    ``get_secret_key`` reads ``HOP3_SECRET_KEY`` from the env, then falls back to
    the config file — so both must be cleared to exercise the failure. monkeypatch
    keeps it hermetic (env is restored after the test).
    """
    monkeypatch.delenv("HOP3_SECRET_KEY", raising=False)
    monkeypatch.setattr("hop3.config.HOP3_SECRET_KEY", None)

    with pytest.raises(ValueError, match="HOP3_SECRET_KEY must be set"):
        create_token("testuser")


# Magic Token Tests


def test_create_magic_token_basic():
    """Test basic magic token creation."""
    token = create_magic_token("admin")
    assert isinstance(token, str)
    assert len(token) > 0
    # Should start with eyJ (JWT header)
    assert token.startswith("eyJ")


def test_create_magic_token_has_magic_link_scope():
    """Test that magic tokens have the magic_link scope."""
    token = create_magic_token("testuser")
    secret_key = get_secret_key()

    payload = jwt.decode(token, secret_key, algorithms=["HS256"])

    assert payload["sub"] == "testuser"
    assert MAGIC_LINK_SCOPE in payload["scopes"]


def test_create_magic_token_short_expiry():
    """Test that magic tokens have a short expiry (5 minutes)."""
    token = create_magic_token("testuser")
    secret_key = get_secret_key()

    payload = jwt.decode(token, secret_key, algorithms=["HS256"])

    # Check expiry is roughly 5 minutes from now
    exp = payload["exp"]
    iat = payload["iat"]
    expected_duration = MAGIC_LINK_EXPIRY_MINUTES * 60

    # Allow 5 second tolerance
    assert abs((exp - iat) - expected_duration) < 5


def test_validate_magic_token_success(monkeypatch):
    """Test successful magic token validation."""
    # Mock is_token_revoked to return False (not revoked).
    # Accepts the new ``scopes=`` kwarg added in 0.5.0.dev3 to give
    # admin/magic-link tokens fail-closed semantics on DB error.
    monkeypatch.setattr(
        "hop3.server.security.tokens.is_token_revoked",
        lambda jti, scopes=None: False,
    )
    # Mock revoke_token to do nothing
    monkeypatch.setattr(
        "hop3.server.security.tokens.revoke_token", lambda jti, exp, reason: None
    )

    token = create_magic_token("admin")
    result = validate_magic_token(token)

    assert result is not None
    assert result["username"] == "admin"


def test_validate_magic_token_invalid():
    """Test validation of invalid magic token."""
    invalid_token = "not.a.valid.token"
    result = validate_magic_token(invalid_token)

    assert result is None


def test_validate_magic_token_wrong_scope(monkeypatch):
    """Test that regular tokens cannot be validated as magic tokens."""
    # Create a regular token (not a magic token)
    regular_token = create_token("testuser", scopes=["authenticated"])

    # Try to validate as magic token
    result = validate_magic_token(regular_token)

    # Should fail because it doesn't have magic_link scope
    assert result is None


def test_validate_magic_token_expired():
    """Test validation of expired magic token."""
    # Create an already-expired magic token
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": "testuser",
        "scopes": [MAGIC_LINK_SCOPE],
        "iat": now - timedelta(minutes=10),
        "exp": now - timedelta(minutes=5),  # Expired 5 minutes ago
        "jti": "test-jti",
    }

    secret_key = get_secret_key()
    expired_token = jwt.encode(expired_payload, secret_key, algorithm="HS256")

    result = validate_magic_token(expired_token)
    assert result is None


def test_validate_magic_token_revoked(monkeypatch):
    """Test that revoked magic tokens are rejected."""
    # Mock is_token_revoked to return True (revoked)
    monkeypatch.setattr(
        "hop3.server.security.tokens.is_token_revoked",
        lambda jti, scopes=None: True,
    )

    token = create_magic_token("admin")
    result = validate_magic_token(token)

    assert result is None


def test_magic_token_unique_jti():
    """Test that magic tokens have unique JTI values."""
    token1 = create_magic_token("admin")
    token2 = create_magic_token("admin")

    secret_key = get_secret_key()
    payload1 = jwt.decode(token1, secret_key, algorithms=["HS256"])
    payload2 = jwt.decode(token2, secret_key, algorithms=["HS256"])

    assert payload1["jti"] != payload2["jti"]
