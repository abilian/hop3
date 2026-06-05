# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Authentication guards for Litestar routes.

Guards are used to protect routes that require authentication.
They check if the user is authenticated before allowing access to the route.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from litestar.exceptions import NotAuthorizedException

from hop3 import config
from hop3.server.security.tokens import validate_token

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection
    from litestar.handlers import BaseRouteHandler


def auth_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    """Guard that requires user authentication.

    Accepts either of the two credentials the platform issues:

    1. A web session cookie (``user_id`` in the session), used by the
       browser dashboard after an interactive login.
    2. An ``Authorization: Bearer <token>`` header, used by the CLI and
       other API clients — the same credential ``/rpc`` accepts.

    Honouring the Bearer token here matters: without it, a token-only
    client (e.g. the CLI streaming deploy logs from ``/api/stream/<id>``)
    failed the guard, the app-wide ``handle_401`` redirected it to
    ``/auth/login`` (302), and the client — which cannot follow a login
    redirect — saw the deploy fail with an opaque stream error instead
    of the real server-side cause.

    If HOP3_UNSAFE is true (testing mode), authentication is skipped.

    Args:
        connection: The ASGI connection with request/session data
        _: The route handler (unused)

    Raises:
        NotAuthorizedException: If neither credential authenticates.
    """
    # Skip authentication in unsafe mode (testing)
    if config.HOP3_UNSAFE:
        return

    # 1. Web session cookie.
    if connection.session.get("user_id"):
        return

    # 2. Bearer token (CLI / API clients).
    if _has_valid_bearer_token(connection):
        return

    raise NotAuthorizedException(detail="Authentication required")


def _has_valid_bearer_token(connection: ASGIConnection) -> bool:
    """Return True iff the request carries a valid ``Bearer`` token.

    Mirrors the validation ``/rpc`` performs (``validate_token``), so the
    two entry points accept exactly the same tokens. No side effects: the
    guard only authorises; it does not mutate the session or issue a
    cookie (a Bearer client neither wants nor expects one).
    """
    auth_header = connection.headers.get("authorization", "")
    # RFC 7235: the auth-scheme is case-insensitive.
    if auth_header[:7].lower() != "bearer ":
        return False
    return bool(validate_token(auth_header[7:].strip()))


def optional_auth_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    """Guard that allows both authenticated and unauthenticated access.

    This guard doesn't raise an exception but can be used to populate
    user context when available. Useful for routes that behave differently
    based on authentication status.

    Args:
        connection: The ASGI connection with request/session data
        _: The route handler (unused)

    Example:
        @get("/maybe-protected", guards=[optional_auth_guard])
        def mixed_route(request: Request) -> dict:
            user_id = request.session.get("user_id")
            if user_id:
                return {"message": "Hello authenticated user"}
            return {"message": "Hello guest"}
    """
    # This guard does nothing - it just ensures session is available
    # The actual auth check is done in the route handler
