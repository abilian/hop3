# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Authentication guards for Litestar routes.

Guards are used to protect routes that require authentication.
They check if the user is authenticated before allowing access to the route.
"""

from __future__ import annotations

from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.handlers import BaseRouteHandler

from hop3 import config


def auth_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    """Guard that requires user authentication.

    This guard checks if the user is authenticated by looking for a user_id
    in the session. If HOP3_UNSAFE is true (testing mode), authentication
    is skipped.

    Args:
        connection: The ASGI connection with request/session data
        _: The route handler (unused)

    Raises:
        NotAuthorizedException: If user is not authenticated

    Example:
        @get("/protected", guards=[auth_guard])
        def protected_route(request: Request) -> dict:
            # This route requires authentication
            return {"message": "You are authenticated"}
    """
    # Skip authentication in unsafe mode (testing)
    if config.HOP3_UNSAFE:
        return

    # Check if user_id exists in session
    user_id = connection.session.get("user_id")
    if not user_id:
        raise NotAuthorizedException(detail="Authentication required")


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
