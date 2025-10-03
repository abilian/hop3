# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Authentication middleware for the Hop3 server.

This middleware validates bearer tokens for API requests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    SimpleUser,
)
from starlette.middleware import Middleware
from starlette.middleware.authentication import (
    AuthenticationMiddleware as StarletteAuthMiddleware,
)

from hop3.server.security.tokens import validate_token

if TYPE_CHECKING:
    from starlette.requests import HTTPConnection


class BearerTokenBackend(AuthenticationBackend):
    """Authentication backend that validates bearer tokens."""

    async def authenticate(self, conn: HTTPConnection):
        """Authenticate the request using a bearer token.

        Args:
            conn: The HTTP connection to authenticate

        Returns:
            Tuple of (auth_credentials, user) if authenticated, None otherwise

        Raises:
            AuthenticationError: If the token is invalid
        """
        # Skip authentication entirely for truly public endpoints
        if self._is_truly_public_endpoint(conn):
            return None

        # Get the Authorization header
        auth_header = conn.headers.get("Authorization")
        if not auth_header:
            # For RPC, we allow missing auth header (some commands are public)
            # The RPC handler will check per-command
            if conn.url.path == "/rpc":
                return None
            raise AuthenticationError("Missing Authorization header")

        # Parse the bearer token
        try:
            scheme, token = auth_header.split(" ", 1)
        except ValueError:
            raise AuthenticationError("Invalid Authorization header format")

        if scheme.lower() != "bearer":
            raise AuthenticationError("Only Bearer authentication is supported")

        # Validate the token
        user_info = validate_token(token)
        if not user_info:
            raise AuthenticationError("Invalid or expired token")

        # Return credentials and user
        scopes = user_info.get("scopes", ["authenticated"])
        username = user_info.get("username", "anonymous")

        return AuthCredentials(scopes), SimpleUser(username)

    def _is_truly_public_endpoint(self, conn: HTTPConnection) -> bool:
        """Check if the endpoint is truly public (no auth header needed at all).

        Args:
            conn: The HTTP connection

        Returns:
            True if the endpoint is truly public, False otherwise
        """
        # Truly public endpoints that never need authentication
        public_paths = [
            "/",  # Home page
            "/static/",  # Static files
            "/health",  # Health check
        ]

        path = conn.url.path
        for public_path in public_paths:
            if path.startswith(public_path):
                return True

        return False


def AuthenticationMiddleware() -> Middleware:
    """Create the authentication middleware.

    Returns:
        Configured authentication middleware
    """
    return Middleware(StarletteAuthMiddleware, backend=BearerTokenBackend())
