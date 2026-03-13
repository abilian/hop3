# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for authentication and user management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar

from hop3.lib.registry import register
from hop3.orm import User
from hop3.orm.repositories import UserRepository
from hop3.server.security.tokens import create_magic_token, create_token

from ._base import Command
from ._response import error, success, text, warning


@register
@dataclass(frozen=True)
class AuthCmd(Command):
    """Authentication commands."""

    name: ClassVar[str] = "auth"
    requires_auth: ClassVar[bool] = False  # Public command (shows help)


@register
@dataclass(frozen=True)
class AuthLoginCmd(Command):
    """Authenticate and receive an API token."""

    user_repo: UserRepository
    name: ClassVar[str] = "auth:login"
    requires_auth: ClassVar[bool] = False  # Public command

    def call(self, username: str = "", password: str = "", *args):
        """Authenticate a user and return an API token.

        Args:
            username: The username to authenticate
            password: The user's password

        Returns:
            Response with token or error message
        """
        if not username or not password:
            return [error("Usage: hop3 auth:login <username> <password>")]

        # Look up the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error("Invalid username or password")]

        # Check if user is active
        if not user.active:
            return [error("Account is disabled")]

        # Verify password
        if not user.check_password(password):
            return [error("Invalid username or password")]

        # Update login tracking
        user.last_login_at = user.current_login_at
        user.current_login_at = datetime.now(timezone.utc)
        user.login_count += 1
        self.user_repo.update(user, auto_commit=True)

        # Generate token
        scopes = ["authenticated"]
        if user.is_admin:
            scopes.append("admin")

        token = create_token(username, scopes=scopes)

        return [
            text(f"Login successful for user: {username}"),
            text(""),
            text("Your API token:"),
            text(token),
            text(""),
            text(
                "Save this token to your config file (~/.config/hop3-cli/config.toml):"
            ),
            text(f'api_token = "{token}"'),
            text(""),
            text("Or set the environment variable:"),
            text(f"export HOP3_API_TOKEN={token}"),
        ]


@register
@dataclass(frozen=True)
class AuthWhoamiCmd(Command):
    """Display current authenticated user information."""

    user_repo: UserRepository
    name: ClassVar[str] = "auth:whoami"
    pass_username: ClassVar[bool] = True  # Needs authenticated username

    def call(self, username: str = "", *args):
        """Display information about the authenticated user.

        This command receives the username from the authentication middleware
        via the RPC context.

        Args:
            username: The username from the authentication context

        Returns:
            User information or error message
        """
        if not username:
            return [error("Not authenticated. Use 'hop3 auth:login' to authenticate.")]

        user = self.user_repo.get_by_username(username)
        if not user:
            return [error("User not found")]

        roles = ", ".join(role.name for role in user.roles) if user.roles else "None"

        return [
            text("Authenticated User Information"),
            text("=" * 40),
            text(f"Username: {user.username}"),
            text(f"Email: {user.email}"),
            text(f"Active: {user.active}"),
            text(f"Roles: {roles}"),
            text(f"Login count: {user.login_count}"),
            text(f"Last login: {user.last_login_at or 'Never'}"),
        ]


@register
@dataclass(frozen=True)
class AuthRegisterCmd(Command):
    """Register a new user account."""

    user_repo: UserRepository
    name: ClassVar[str] = "auth:register"
    requires_auth: ClassVar[bool] = False  # Public command

    def call(self, username: str = "", email: str = "", password: str = "", *args):
        """Register a new user.

        Args:
            username: Desired username
            email: User's email address
            password: User's password

        Returns:
            Success message or error
        """
        if not username or not email or not password:
            return [error("Usage: hop3 auth:register <username> <email> <password>")]

        # Check if username already exists
        if self.user_repo.username_exists(username):
            return [error(f"Username '{username}' already exists")]

        # Check if email already exists
        if self.user_repo.email_exists(email):
            return [error(f"Email '{email}' already registered")]

        # Create new user
        user = User(username=username, email=email, password_hash="")
        user.set_password(password)
        user.active = True
        user.confirmed_at = datetime.now(timezone.utc)

        self.user_repo.add(user, auto_commit=True)

        return [
            text(f"User '{username}' registered successfully!"),
            text(""),
            text("You can now login with:"),
            text(f"hop3 auth:login {username} <password>"),
        ]


@register
@dataclass(frozen=True)
class AuthLogoutCmd(Command):
    """Logout (invalidate current token).

    This command revokes the current token, making it immediately invalid
    even before its expiration time. The token is added to a revocation list
    and will be rejected by the authentication middleware.
    """

    name: ClassVar[str] = "auth:logout"
    pass_username: ClassVar[bool] = True  # Request passes the username from the token
    pass_token_info: ClassVar[bool] = True  # Request passes the full token

    def call(self, username: str, _token: str | None = None):
        """Logout the current user by revoking their token.

        Args:
            username: The authenticated username (injected by RPC handler)
            _token: The JWT token (injected by RPC handler, starts with _)

        Returns:
            Logout success message
        """
        from datetime import datetime, timezone  # noqa: PLC0415

        import jwt  # noqa: PLC0415

        from hop3.server.security.tokens import (  # noqa: PLC0415
            get_secret_key,
            revoke_token,
        )

        # Decode the token to get jti and expiration
        if _token:
            try:
                secret_key = get_secret_key()
                payload = jwt.decode(
                    _token,
                    secret_key,
                    algorithms=["HS256"],
                    options={"verify_exp": False},
                )

                jti = payload.get("jti")
                exp = payload.get("exp")

                if jti and exp:
                    # Convert expiration timestamp to datetime
                    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)

                    # Revoke the token
                    revoke_token(jti, expires_at, reason="user_logout")

                    return [
                        success(f"Logged out user: {username}"),
                        text(""),
                        text("Your token has been revoked and is no longer valid."),
                        text(""),
                        text("Remove the token from your config file or environment:"),
                        text(
                            "  - Delete 'api_token' from ~/.config/hop3-cli/config.toml"
                        ),
                        text("  - Or unset HOP3_API_TOKEN environment variable"),
                    ]
            except Exception:
                pass  # Fall through to generic message

        # Fallback if token couldn't be revoked
        return [
            text(f"Logged out user: {username}"),
            text(""),
            text("Remove the token from your config file or environment:"),
            text("  - Delete 'api_token' from ~/.config/hop3-cli/config.toml"),
            text("  - Or unset HOP3_API_TOKEN environment variable"),
            text(""),
            warning("Note: Token revocation requires a valid JWT with jti claim."),
        ]


@register
@dataclass(frozen=True)
class AuthMagicLinkCmd(Command):
    """Generate a magic link for passwordless web login.

    This command generates a short-lived token that can be used to log into
    the web dashboard without entering a password. The token expires after
    5 minutes and can only be used once.

    This is typically called via SSH from the command line:
        ssh user@server hop3-server auth:magic-link

    Or via the CLI:
        hop3 login --web
    """

    user_repo: UserRepository
    name: ClassVar[str] = "auth:magic-link"
    requires_auth: ClassVar[bool] = False  # Called via SSH, not authenticated RPC

    def call(self, username: str = "admin", *args):
        """Generate a magic link token for web login.

        Args:
            username: The username to generate the link for (default: admin)

        Returns:
            Response with magic token or error message
        """
        # Look up the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        # Check if user is active
        if not user.active:
            return [error(f"User '{username}' is disabled")]

        # Generate magic link token
        token = create_magic_token(username)

        # Return just the token - the CLI or caller will construct the full URL
        return [
            text(token),
        ]
