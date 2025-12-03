# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for JWT token generation and validation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from hop3.server.security.tokens import create_token, generate_api_key, validate_token


@pytest.fixture(autouse=True)
def setup_secret_key():
    """Set up a test secret key."""
    os.environ["HOP3_SECRET_KEY"] = "test-secret-key-for-testing-only"
    yield
    os.environ.pop("HOP3_SECRET_KEY", None)


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
    os.environ["HOP3_SECRET_KEY"] = "different-secret-key"
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


@pytest.mark.skip(reason="Relying on environment variable is not ideal for tests")
def test_create_token_without_secret_key():
    """Test that token creation fails without a secret key."""
    os.environ.pop("HOP3_SECRET_KEY", None)

    with pytest.raises(ValueError, match="HOP3_SECRET_KEY must be set"):
        create_token("testuser")
