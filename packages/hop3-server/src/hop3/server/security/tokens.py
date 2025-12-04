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
from typing import Any

import jwt


def _get_config():
    """Lazy import to avoid circular dependency."""
    from hop3 import config as c  # noqa: PLC0415

    return c


# Valid scopes that can be assigned to tokens
VALID_SCOPES = {"authenticated", "admin", "user"}


def get_secret_key() -> str:
    """Get the secret key for token signing.

    Checks environment variable first (for tests and overrides),
    then falls back to config file.

    Returns:
        The secret key from config or environment

    Raises:
        ValueError: If no secret key is configured
    """
    # Check environment first (for tests and dynamic overrides)
    secret = os.environ.get("HOP3_SECRET_KEY")

    # Fall back to config file
    if not secret:
        c = _get_config()
        secret = c.HOP3_SECRET_KEY

    if not secret:
        msg = (
            "HOP3_SECRET_KEY must be set in configuration or environment. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
        raise ValueError(msg)
    return secret


def create_token(
    username: str, scopes: list[str] | None = None, expires_hours: int = 24
) -> str:
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

    This function:
    1. Decodes and validates the JWT structure
    2. Checks the revocation list to ensure the token hasn't been revoked
    3. Validates scopes and claims

    Args:
        token: The JWT token string to validate

    Returns:
        The token payload if valid and not revoked, None otherwise
    """
    try:
        secret_key = get_secret_key()

        # Decode with strict validation
        # - algorithms=["HS256"]: Only allow HS256, prevents "none" algorithm attack
        # - options: Require specific claims
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            options={
                "require": ["exp", "sub"],  # Require expiration and subject
            },
        )

        # Check if token is revoked (if jti is present)
        jti = payload.get("jti")
        if jti and is_token_revoked(jti):
            return None

        # Validate that the token has proper scopes
        scopes = payload.get("scopes", [])
        if not isinstance(scopes, list):
            return None

        # Scopes list must not be empty
        if not scopes:
            return None

        # At least one scope must be valid
        if not any(scope in VALID_SCOPES for scope in scopes):
            return None

        # Extract user info from payload
        return {
            "username": payload.get("sub"),
            "scopes": scopes,
            "issued_at": payload.get("iat"),
            "expires_at": payload.get("exp"),
            "token_id": jti,
        }
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
        # Token has expired, is invalid, or secret key not configured
        return None
    except Exception:
        # Unexpected error
        return None


def is_token_revoked(jti: str) -> bool:
    """Check if a token has been revoked.

    Args:
        jti: JWT ID to check

    Returns:
        True if the token is revoked, False otherwise
    """
    from hop3.orm import RevokedToken  # noqa: PLC0415
    from hop3.server.lib.database import get_session  # noqa: PLC0415

    try:
        with get_session() as db_session:
            revoked = (
                db_session.query(RevokedToken).filter_by(jti=jti).first() is not None
            )
            return revoked
    except Exception:
        # If there's a database error, fail open (allow the token)
        # This prevents a database outage from locking out all users
        return False


def revoke_token(jti: str, expires_at: datetime, reason: str | None = None) -> None:
    """Revoke a token by adding it to the revocation list.

    Args:
        jti: JWT ID to revoke
        expires_at: When the token expires (for cleanup)
        reason: Optional reason for revocation (e.g., "user_logout")
    """
    from hop3.orm import RevokedToken  # noqa: PLC0415
    from hop3.server.lib.database import get_session  # noqa: PLC0415

    with get_session() as db_session:
        # Check if already revoked
        existing = db_session.query(RevokedToken).filter_by(jti=jti).first()
        if existing:
            return  # Already revoked

        # Add to revocation list
        revoked_token = RevokedToken(
            jti=jti,
            expires_at=expires_at,
            reason=reason,
        )
        db_session.add(revoked_token)
        db_session.commit()


def generate_api_key() -> str:
    """Generate a random API key for long-lived tokens.

    Returns:
        A URL-safe random API key
    """
    return secrets.token_urlsafe(32)
