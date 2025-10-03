# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Token generation and validation for authentication.

This module provides JWT-based token authentication for the Hop3 API.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import jwt

if TYPE_CHECKING:
    pass


def get_secret_key() -> str:
    """Get the secret key for token signing.

    Returns:
        The secret key from config or environment

    Raises:
        ValueError: If no secret key is configured
    """
    # Read directly from environment to support test fixtures
    secret = os.environ.get("HOP3_SECRET_KEY", "")
    if not secret:
        msg = (
            "HOP3_SECRET_KEY must be set in configuration or environment. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
        raise ValueError(msg)
    return secret


def create_token(username: str, scopes: list[str] | None = None, expires_hours: int = 24) -> str:
    """Create a JWT token for a user.

    Args:
        username: The username to create the token for
        scopes: List of permission scopes (default: ["authenticated"])
        expires_hours: Number of hours until the token expires (default: 24)

    Returns:
        The JWT token string
    """
    if scopes is None:
        scopes = ["authenticated"]

    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=expires_hours)

    payload = {
        "sub": username,  # Subject (username)
        "scopes": scopes,
        "iat": now,  # Issued at
        "exp": expiry,  # Expiration
        "jti": secrets.token_urlsafe(16),  # JWT ID (unique token identifier)
    }

    secret_key = get_secret_key()
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return token


def validate_token(token: str) -> dict[str, Any] | None:
    """Validate a JWT token and return the payload.

    Args:
        token: The JWT token string to validate

    Returns:
        The token payload if valid, None otherwise
    """
    try:
        secret_key = get_secret_key()
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])

        # Extract user info from payload
        return {
            "username": payload.get("sub"),
            "scopes": payload.get("scopes", ["authenticated"]),
            "issued_at": payload.get("iat"),
            "expires_at": payload.get("exp"),
            "token_id": payload.get("jti"),
        }
    except jwt.ExpiredSignatureError:
        # Token has expired
        return None
    except jwt.InvalidTokenError:
        # Token is invalid
        return None
    except ValueError:
        # Secret key not configured
        return None


def generate_api_key() -> str:
    """Generate a random API key for long-lived tokens.

    Returns:
        A URL-safe random API key
    """
    return secrets.token_urlsafe(32)
