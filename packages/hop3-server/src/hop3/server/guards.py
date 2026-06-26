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
from hop3.server.security.web_auth import current_identity

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection
    from litestar.handlers import BaseRouteHandler


def auth_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    """Guard that requires user authentication.

    Accepts the single signed credential the platform issues, over either
    transport (``hop3.server.security.web_auth.current_identity``):

    1. The ``hop3_auth`` cookie, set by the browser dashboard after login.
    2. An ``Authorization: Bearer <token>`` header, used by the CLI and
       other API clients — the same JWT ``/rpc`` accepts.

    Honouring the Bearer token here matters: without it, a token-only
    client (e.g. the CLI streaming deploy logs from ``/api/stream/<id>``)
    failed the guard, the app-wide ``handle_401`` redirected it to
    ``/auth/login`` (302), and the client — which cannot follow a login
    redirect — saw the deploy fail with an opaque stream error instead
    of the real server-side cause.

    The credential is stateless: a signed JWT, validated with the persistent
    server secret. No server-side session is consulted.

    If HOP3_UNSAFE is true (testing mode), authentication is skipped.

    Args:
        connection: The ASGI connection
        _: The route handler (unused)

    Raises:
        NotAuthorizedException: If the request carries no valid credential.
    """
    # Skip authentication in unsafe mode (testing)
    if config.HOP3_UNSAFE:
        return

    if current_identity(connection):
        return

    raise NotAuthorizedException(detail="Authentication required")


def optional_auth_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    """Guard that allows both authenticated and unauthenticated access.

    This guard doesn't raise an exception but can be used to populate
    user context when available. Useful for routes that behave differently
    based on authentication status.

    Args:
        connection: The ASGI connection
        _: The route handler (unused)

    Example:
        @get("/maybe-protected", guards=[optional_auth_guard])
        def mixed_route(request: Request) -> dict:
            if current_identity(request):
                return {"message": "Hello authenticated user"}
            return {"message": "Hello guest"}
    """
    # This guard does nothing - the actual auth check is done in the handler
    # (e.g. via current_identity).
