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
from starlette.responses import JSONResponse

from hop3 import config
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
        # UNSAFE MODE: Skip authentication entirely if HOP3_UNSAFE is true
        # WARNING: This should ONLY be used in testing environments
        if config.HOP3_UNSAFE:
            return AuthCredentials(["authenticated", "admin"]), SimpleUser(
                "unsafe-test-user"
            )

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
            msg = "Missing Authorization header"
            raise AuthenticationError(msg)

        # Parse the bearer token
        try:
            scheme, token = auth_header.split(" ", 1)
        except ValueError:
            # For RPC, allow through with invalid header format
            # The RPC handler will reject if the command requires auth
            if conn.url.path == "/rpc":
                return None
            msg = "Invalid Authorization header format"
            raise AuthenticationError(msg)

        if scheme.lower() != "bearer":
            # For RPC, allow through with invalid scheme
            # The RPC handler will reject if the command requires auth
            if conn.url.path == "/rpc":
                return None
            msg = "Only Bearer authentication is supported"
            raise AuthenticationError(msg)

        # Strip whitespace from token
        token = token.strip()

        # Validate the token
        user_info = validate_token(token)
        if not user_info:
            # For RPC, allow through with invalid token
            # This allows public commands (auth:register, auth:login) to work
            # even if the user has an expired token in their config
            # The RPC handler will reject if the command requires auth
            if conn.url.path == "/rpc":
                return None
            msg = "Invalid or expired token"
            raise AuthenticationError(msg)

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
        path = conn.url.path

        # Exact match for home page
        if path == "/":
            return True

        # Prefix match for static files and health
        public_prefixes = [
            "/static/",  # Static files
            "/health",  # Health check (exact or with query params)
        ]

        return any(path.startswith(prefix) for prefix in public_prefixes)


def on_auth_error(conn: HTTPConnection, exc: AuthenticationError) -> JSONResponse:
    """Custom error handler that returns 401 instead of 400.

    Args:
        conn: The HTTP connection
        exc: The authentication error

    Returns:
        JSON response with 401 status code
    """
    return JSONResponse(
        {"detail": str(exc)},
        status_code=401,
    )
