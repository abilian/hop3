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
from pathlib import Path
from typing import Any

import jwt

# ADR 048: the JWT signing key's canonical home is a secrets-tier file,
# root:hop3 0640, read identically by the running service AND the su-hop3 CLI.
# Making it the highest-precedence source ends the legacy split where the
# service read the key from the environment while the CLI read it from
# hop3-server.toml (a partial install could desync the two → silent 401s).
SECRET_KEY_FILE = Path("/etc/hop3/secret-key")


def _get_config():
    """Lazy import to avoid circular dependency."""
    from hop3 import config as c  # noqa: PLC0415

    return c


def _read_secret_key_file() -> str | None:
    """Return the signing key from the canonical secrets file, or None.

    Any IO error — absent file (legacy install, dev/CI host), no permission —
    yields None so the environment / hop3-server.toml fallbacks still apply.
    """
    try:
        return SECRET_KEY_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


# Valid scopes that can be assigned to general-purpose tokens.
# `magic_link` is intentionally excluded — magic-link tokens go through
# `validate_magic_token`, not the general bearer-auth path. Letting them
# satisfy `validate_token` would let a redeemable magic link act as a
# 5-minute bearer for any RPC command (security review C-001/H-001).
VALID_SCOPES = {"authenticated", "admin", "user"}

# Magic link configuration
MAGIC_LINK_SCOPE = "magic_link"
MAGIC_LINK_EXPIRY_MINUTES = 5


def get_secret_key() -> str:
    """Get the secret key for token signing.

    Resolution order (ADR 048): the canonical ``/etc/hop3/secret-key`` file
    first, then the ``HOP3_SECRET_KEY`` environment variable (tests, overrides,
    legacy installs), then ``hop3-server.toml`` (legacy fallback).

    Returns:
        The secret key.

    Raises:
        ValueError: If no secret key is configured in any source.
    """
    # 1. Canonical secrets-tier file (ADR 048): one source read by both the
    #    running service and the su-hop3 CLI.
    secret = _read_secret_key_file()

    # 2. Environment: tests, explicit overrides, and legacy installs that still
    #    inject HOP3_SECRET_KEY via /etc/default/hop3.
    if not secret:
        secret = os.environ.get("HOP3_SECRET_KEY")

    # 3. Legacy fallback: hop3-server.toml (pre-ADR-048 installs wrote it there).
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
    username: str,
    scopes: list[str] | None = None,
    expires_hours: int | None = None,
) -> str:
    """Create a JWT token for a user.

    Args:
        username: The username to create the token for
        scopes: List of permission scopes (default: ["authenticated"])
        expires_hours: Override the configured expiry. When None, reads
            ``HOP3_TOKEN_EXPIRY_HOURS`` from config (default: 24).

    Returns:
        The JWT token string
    """
    if scopes is None:
        scopes = ["authenticated"]

    if expires_hours is None:
        expires_hours = _get_config().HOP3_TOKEN_EXPIRY_HOURS

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


def validate_token(token: str) -> dict[str, Any] | None:  # noqa: PLR0911 — security-critical: every early `return None` is a distinct validation rule failing (revocation, scopes shape, empty scopes, no valid scope, ExpiredSignature/InvalidToken, generic catch-all). Coalescing them into a single return path risks accidentally weakening one of the rules; multiple early-exits are the right pattern here.
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

        # Check if token is revoked (if jti is present).
        # SECURITY: pass the token's scopes so admin-scoped tokens fail
        # *closed* on a DB error while user-scoped tokens fail open
        # (avoiding lockout-on-DB-outage). See is_token_revoked.
        jti = payload.get("jti")
        token_scopes = payload.get("scopes", []) or []
        if jti and is_token_revoked(jti, scopes=token_scopes):
            return None

        # Subject (username) must be a non-empty string — `require: ["sub"]`
        # only ensures the claim is present, not that it carries a real user.
        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub:
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
            "username": sub,
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


def is_token_revoked(jti: str, scopes: list[str] | None = None) -> bool:
    """Check if a token has been revoked.

    SECURITY: on a DB error this fails *open* for normal user tokens
    (so a DB outage does not lock every authenticated user out of
    their own apps), but fails *closed* for tokens carrying the
    ``admin`` scope. The blast radius of an admin-scope false-allow
    is significantly larger than a user-scope false-deny, so the
    asymmetry is the right default. Surfaced from 0.5dev3 / 0.5.0.dev3
    triage; see notes/security.md §3.3.
    """
    from hop3.orm.repositories import RevokedTokenRepository  # noqa: PLC0415
    from hop3.server.lib.database import get_session  # noqa: PLC0415

    try:
        with get_session() as db_session:
            repo = RevokedTokenRepository(session=db_session)
            return repo.is_revoked(jti)
    except Exception:
        is_admin = scopes is not None and "admin" in scopes
        # Admin scope: fail closed (treat as revoked).
        # User scope: fail open (treat as not revoked) so a DB
        # outage doesn't lock everyone out.
        return is_admin


def revoke_token(jti: str, expires_at: datetime, reason: str | None = None) -> None:
    """Revoke a token by adding it to the revocation list.

    Args:
        jti: JWT ID to revoke
        expires_at: When the token expires (for cleanup)
        reason: Optional reason for revocation (e.g., "user_logout")
    """
    from hop3.orm import RevokedToken  # noqa: PLC0415
    from hop3.orm.repositories import RevokedTokenRepository  # noqa: PLC0415
    from hop3.server.lib.database import get_session  # noqa: PLC0415

    with get_session() as db_session:
        repo = RevokedTokenRepository(session=db_session)

        # Check if already revoked
        if repo.is_revoked(jti):
            return  # Already revoked

        # Add to revocation list
        revoked_token = RevokedToken(
            jti=jti,
            expires_at=expires_at,
            reason=reason,
        )
        repo.add(revoked_token, auto_commit=True)


def revoke_jwt(token: str, reason: str | None = None) -> bool:
    """Decode a (possibly expired) JWT and revoke it by ``jti``.

    The single decode-and-revoke used by BOTH logout paths (CLI and web) so they
    stay symmetric — a logout invalidates the token, it doesn't merely drop the
    local copy. The signature is verified with the server key (a forged/garbage
    token can't poison the revocation list) but expiry is NOT (``verify_exp``
    off), so a near-expiry token is still revoked.

    Args:
        token: The JWT to revoke.
        reason: Optional reason recorded on the revocation entry.

    Returns:
        True if the token was decoded and revoked, False if it couldn't be
        decoded or lacked a ``jti``/``exp``.
    """
    try:
        payload = jwt.decode(
            token,
            get_secret_key(),
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError:
        return False

    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return False

    revoke_token(jti, datetime.fromtimestamp(exp, tz=timezone.utc), reason=reason)
    return True


def generate_api_key() -> str:
    """Generate a random API key for long-lived tokens.

    Returns:
        A URL-safe random API key
    """
    return secrets.token_urlsafe(32)


def create_magic_token(username: str) -> str:
    """Create a short-lived magic link token for web login.

    Magic tokens:
    - Expire in 5 minutes
    - Have the special "magic_link" scope
    - Are single-use (validated once, then revoked)

    Args:
        username: The username to create the token for

    Returns:
        The JWT token string
    """
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(minutes=MAGIC_LINK_EXPIRY_MINUTES)

    payload = {
        "sub": username,
        "scopes": [MAGIC_LINK_SCOPE],
        "iat": now,
        "exp": expiry,
        "jti": secrets.token_urlsafe(16),
    }

    secret_key = get_secret_key()
    return jwt.encode(payload, secret_key, algorithm="HS256")


def validate_magic_token(token: str) -> dict[str, Any] | None:
    """Validate a magic link token and mark it as used.

    This function validates the token and immediately revokes it to ensure
    single-use behavior.

    Args:
        token: The JWT token string to validate

    Returns:
        Dict with "username" if valid, None otherwise
    """
    try:
        secret_key = get_secret_key()

        payload = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )

        # Validate that this is a magic link token
        scopes = payload.get("scopes", [])
        # Check if token is revoked. Magic links are bootstrap tokens
        # (single-use, 5-min validity), so we want fail-closed semantics
        # — pass MAGIC_LINK_SCOPE as if it were admin to get that
        # treatment from is_token_revoked.
        jti = payload.get("jti")
        if jti and is_token_revoked(jti, scopes=["admin", *scopes]):
            return None
        if MAGIC_LINK_SCOPE not in scopes:
            return None

        # Immediately revoke the token (single-use)
        if jti:
            expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            revoke_token(jti, expires_at, reason="magic_link_used")

        return {"username": payload.get("sub")}

    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
        return None
    except Exception:
        return None
