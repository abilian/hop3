# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for authentication and user management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from hop3.lib.registry import register
from hop3.orm import User
from hop3.server.security.tokens import create_token

from ._base import Command

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@register
@dataclass(frozen=True)
class AuthCmd(Command):
    """Authentication commands."""

    name = "auth"


@register
@dataclass(frozen=True)
class AuthLoginCmd(Command):
    """Authenticate and receive an API token."""

    db_session: Session
    name = "auth:login"

    def call(self, username: str = "", password: str = "", *args):
        """Authenticate a user and return an API token.

        Args:
            username: The username to authenticate
            password: The user's password

        Returns:
            Response with token or error message
        """
        if not username or not password:
            return [
                {
                    "t": "error",
                    "text": "Usage: hop3 auth:login <username> <password>",
                }
            ]

        # Look up the user
        user = self.db_session.query(User).filter_by(username=username).first()
        if not user:
            return [{"t": "error", "text": "Invalid username or password"}]

        # Check if user is active
        if not user.active:
            return [{"t": "error", "text": "Account is disabled"}]

        # Verify password
        if not user.check_password(password):
            return [{"t": "error", "text": "Invalid username or password"}]

        # Update login tracking
        user.last_login_at = user.current_login_at
        user.current_login_at = datetime.now(timezone.utc)
        user.login_count += 1
        self.db_session.commit()

        # Generate token
        scopes = ["authenticated"]
        if user.is_admin:
            scopes.append("admin")

        token = create_token(username, scopes=scopes)

        return [
            {"t": "text", "text": f"Login successful for user: {username}"},
            {"t": "text", "text": ""},
            {"t": "text", "text": "Your API token:"},
            {"t": "text", "text": token},
            {"t": "text", "text": ""},
            {
                "t": "text",
                "text": "Save this token to your config file (~/.config/hop3-cli/config.toml):",
            },
            {"t": "text", "text": f'api_token = "{token}"'},
            {"t": "text", "text": ""},
            {"t": "text", "text": "Or set the environment variable:"},
            {"t": "text", "text": f"export HOP3_API_TOKEN={token}"},
        ]


@register
@dataclass(frozen=True)
class AuthWhoamiCmd(Command):
    """Display current authenticated user information."""

    db_session: Session
    name = "auth:whoami"

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
            return [
                {
                    "t": "error",
                    "text": "Not authenticated. Use 'hop3 auth:login' to authenticate.",
                }
            ]

        user = self.db_session.query(User).filter_by(username=username).first()
        if not user:
            return [{"t": "error", "text": "User not found"}]

        roles = ", ".join(role.name for role in user.roles) if user.roles else "None"

        return [
            {"t": "text", "text": "Authenticated User Information"},
            {"t": "text", "text": "=" * 40},
            {"t": "text", "text": f"Username: {user.username}"},
            {"t": "text", "text": f"Email: {user.email}"},
            {"t": "text", "text": f"Active: {user.active}"},
            {"t": "text", "text": f"Roles: {roles}"},
            {"t": "text", "text": f"Login count: {user.login_count}"},
            {
                "t": "text",
                "text": f"Last login: {user.last_login_at or 'Never'}",
            },
        ]


@register
@dataclass(frozen=True)
class AuthRegisterCmd(Command):
    """Register a new user account."""

    db_session: Session
    name = "auth:register"

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
            return [
                {
                    "t": "error",
                    "text": "Usage: hop3 auth:register <username> <email> <password>",
                }
            ]

        # Check if username already exists
        existing_user = self.db_session.query(User).filter_by(username=username).first()
        if existing_user:
            return [{"t": "error", "text": f"Username '{username}' already exists"}]

        # Check if email already exists
        existing_email = self.db_session.query(User).filter_by(email=email).first()
        if existing_email:
            return [{"t": "error", "text": f"Email '{email}' already registered"}]

        # Create new user
        user = User(username=username, email=email, password_hash="")
        user.set_password(password)
        user.active = True
        user.confirmed_at = datetime.now(timezone.utc)

        self.db_session.add(user)
        self.db_session.commit()

        return [
            {"t": "text", "text": f"User '{username}' registered successfully!"},
            {"t": "text", "text": ""},
            {"t": "text", "text": "You can now login with:"},
            {"t": "text", "text": f"hop3 auth:login {username} <password>"},
        ]


@register
@dataclass(frozen=True)
class AuthLogoutCmd(Command):
    """Logout (invalidate current token)."""

    name = "auth:logout"

    def call(self, *args):
        """Logout the current user.

        Note: With JWT tokens, logout is client-side only. The token will
        expire based on its expiration time. For immediate invalidation,
        a token revocation list would be needed.

        Returns:
            Logout instructions
        """
        return [
            {"t": "text", "text": "Logout successful"},
            {"t": "text", "text": ""},
            {
                "t": "text",
                "text": "Remove the token from your config file or environment:",
            },
            {
                "t": "text",
                "text": "  - Delete 'api_token' from ~/.config/hop3-cli/config.toml",
            },
            {"t": "text", "text": "  - Or unset HOP3_API_TOKEN environment variable"},
            {"t": "text", "text": ""},
            {
                "t": "text",
                "text": "Note: The token will remain valid until it expires.",
            },
        ]
