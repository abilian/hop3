# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for authentication and user management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar

from hop3.lib.registry import register

# Runtime import for Dishka DI (not just type hint)
from hop3.orm.repositories import UserRepository  # noqa: TC001
from hop3.server.security.tokens import create_magic_token, create_token

from ._base import Command
from ._response import error, success, text, warning
from .user import require_admin


@register
@dataclass(frozen=True)
class AuthCmd(Command):
    """Authentication commands.

    Examples:
        hop3 auth login                # Log in (alias: hop3 login)
        hop3 auth whoami               # Show the current user
        hop3 auth logout               # Log out (alias: hop3 logout)
        hop3 auth get-token alice      # Print a token for scripts/automation
    """

    name: ClassVar[tuple[str, ...]] = ("auth",)
    requires_auth: ClassVar[bool] = False  # Public command (shows help)


@register
@dataclass(frozen=True)
class AuthGetTokenCmd(Command):
    """Verify credentials and print an API token (for scripts / automation).

    This is the non-interactive primitive behind the interactive `hop3 login`
    flow: it takes a username and password and returns a token. It does NOT
    write any local config — it just prints the token. To actually log in
    (token saved to your context), use `hop3 login` / `hop3 auth login`.

    Pass the password without putting it on the command line:
        hop3 auth get-token alice --password-file -    # read from stdin
        hop3 auth get-token alice --password-file pw    # read from a file
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("auth", "get-token")
    requires_auth: ClassVar[bool] = False  # Public command

    def call(self, username: str = "", password: str = "", *args):
        """Verify credentials and return an API token.

        Args:
            username: The username to authenticate
            password: The user's password

        Returns:
            Response with token or error message
        """
        if not username or not password:
            return [error("Usage: hop3 auth get-token <username> <password>")]

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

        # Print only the token so callers can capture it directly, e.g.
        #   TOKEN=$(hop3 auth get-token alice --password-file -)
        return [text(token)]


@register
@dataclass(frozen=True)
class AuthWhoamiCmd(Command):
    """Display current authenticated user information.

    Examples:
        hop3 auth whoami               # Show the currently-authenticated user
        hop3 whoami                    # Same via top-level alias
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("auth", "whoami")
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
            return [error("Not authenticated. Use 'hop3 auth login' to authenticate.")]

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


# `auth register` was a duplicate of `user add` (ADR 036 P2.1): both are
# admin-gated account creation. Dropped — `("auth", "register")` is now a
# back-compat alias of `UserAddCmd` (see commands/user.py). `user add` is the
# single canonical path (ADR D4: users are *registered*, not *created*).


@register
@dataclass(frozen=True)
class AuthLogoutCmd(Command):
    """Logout (invalidate current token).

    This command revokes the current token, making it immediately invalid
    even before its expiration time. The token is added to a revocation list
    and will be rejected by the authentication middleware.


    Examples:
        hop3 auth logout               # Invalidate the current session token
    """

    name: ClassVar[tuple[str, ...]] = ("auth", "logout")
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
        from hop3.server.security.tokens import revoke_jwt  # noqa: PLC0415

        # Revoke the token (shared with the web logout path so both invalidate,
        # not merely drop, the credential).
        if _token and revoke_jwt(_token, reason="user_logout"):
            return [
                success(f"Logged out user: {username}"),
                text(""),
                text("Your token has been revoked and is no longer valid."),
                text(""),
                text("Remove the token from your config file or environment:"),
                text("  - Delete 'api_token' from ~/.config/hop3-cli/config.toml"),
                text("  - Or unset HOP3_API_TOKEN environment variable"),
            ]

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
        ssh user@server hop3-server auth magic-link

    Or via the CLI:
        hop3 login --web


    Examples:
        hop3 auth magic-link user@example.com
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("auth", "magic-link")
    requires_auth: ClassVar[bool] = True
    # Admin-gated: the RPC layer must inject the *verified* caller identity into
    # `authenticated_username`. Without this the attacker-supplied first
    # positional lands there and `require_admin` checks a name of the caller's
    # choosing (e.g. "admin") — a privilege-escalation path to mint a magic
    # token for any user. (Audit 2026-06 A1.)
    pass_username: ClassVar[bool] = True
    # Internal primitive behind `hop3 login --web`; off the user-visible surface.
    hidden: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Generate a magic link token for web login. Admin-only.

        Args:
            authenticated_username: The authenticated user (admin-gated).
            username: The username to generate the link for. Required.

        Returns:
            Response with magic token or error message
        """
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not username:
            return [error("Usage: hop3 auth magic-link <username>")]

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
