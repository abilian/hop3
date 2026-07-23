# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Stateless web authentication — the dashboard identity rides a signed JWT.

Authentication does not depend on any server-side session. The browser holds
the same kind of signed token the CLI uses (minted by ``create_token``, checked
by ``validate_token``) in an httponly cookie. Because the token is signed with
the persistent server secret key (``/etc/hop3/secret-key``), it stays valid
across restarts and redeploys and needs no server-side store — so a redeploy no
longer logs everyone out.

One credential, two transports: an ``Authorization: Bearer`` header (CLI / API)
or the ``hop3_auth`` cookie (browser). ``current_identity`` is the single answer
to "who is this request", used by the route guard, the RPC controller, and the
templates alike.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from litestar.datastructures import Cookie

from hop3.config import HOP3_DEBUG
from hop3.server.security.tokens import create_token, validate_token

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection

# Cookie carrying the web auth token. Browsers can't send an Authorization
# header, so the same JWT travels in this cookie instead.
AUTH_COOKIE = "hop3_auth"

# Web sessions outlive the 24h CLI-token default; this matches the dashboard's
# previous 14-day session lifetime.
WEB_SESSION_EXPIRY_HOURS = 24 * 14
_MAX_AGE_SECONDS = WEB_SESSION_EXPIRY_HOURS * 3600


def issue_web_token(username: str) -> str:
    """A signed JWT identifying ``username`` for the dashboard cookie."""
    return create_token(username, expires_hours=WEB_SESSION_EXPIRY_HOURS)


def extract_token(connection: ASGIConnection) -> str | None:
    """
    The bearer JWT for this request, from the header or the auth cookie.

    The ``Authorization`` header wins — an API client that sends one neither
    wants nor expects cookie behaviour.
    """
    auth_header = connection.headers.get("authorization", "")
    # RFC 7235: the auth-scheme is case-insensitive. A header with an *empty*
    # token falls through to the cookie rather than masking a valid one.
    if auth_header[:7].lower() == "bearer ":
        token = auth_header[7:].strip()
        if token:
            return token
    return connection.cookies.get(AUTH_COOKIE) or None


def current_identity(connection: ASGIConnection) -> dict[str, Any] | None:
    """
    The authenticated identity for this request, or None.

    Stateless: validates the JWT from the cookie or the ``Authorization``
    header. No server-side session is consulted. Returns the token payload
    (notably ``username`` and ``scopes``) when valid.
    """
    token = extract_token(connection)
    if not token:
        return None
    return validate_token(token)


def auth_cookie(username: str) -> Cookie:
    """The ``Set-Cookie`` carrying a fresh web token for ``username`` (login)."""
    return Cookie(
        key=AUTH_COOKIE,
        value=issue_web_token(username),
        max_age=_MAX_AGE_SECONDS,
        httponly=True,
        secure=not HOP3_DEBUG,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie() -> Cookie:
    """The ``Set-Cookie`` that deletes the web token (logout)."""
    return Cookie(
        key=AUTH_COOKIE,
        value="",
        max_age=0,
        httponly=True,
        secure=not HOP3_DEBUG,
        samesite="lax",
        path="/",
    )
