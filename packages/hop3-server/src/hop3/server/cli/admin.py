# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Server-side CLI commands for admin user management.

These commands run directly on the server and provide bootstrap capabilities
for creating the first admin user without requiring HTTP authentication.

See ADR 014 for the design rationale.
"""

from __future__ import annotations

import getpass
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from hop3.commands.auth import member_token_refusal
from hop3.core.roles import Role
from hop3.lib.registry import register
from hop3.orm import User
from hop3.orm.repositories import UserRepository
from hop3.server.lib.database import get_session
from hop3.server.security.tokens import create_magic_token, create_token

from ._base import Command

if TYPE_CHECKING:
    from argparse import ArgumentParser


@register
class Admin(Command):
    """
    Manage admin users and authentication tokens.

    Subcommands:
        admin:create         Create a new admin user
        admin:token          Generate a new token for an existing user
        admin:list           List all users
        admin:reset-password Reset a user's password
        admin:server-url     Print the server's public base URL

    Use 'hop3-server admin:<subcommand> --help' for details.
    """

    name = "admin"

    # No run method - Help class will show subcommands


@register
class AdminCreate(Command):
    """
    Create an admin user and display an API token.

    Usage:
        hop3-server admin:create <username> <email> [--password-stdin]

    This command creates a new admin user with the specified username and email.
    The password can be provided interactively (prompted) or via stdin for
    automation.

    Examples:
        # Interactive (prompts for password)
        hop3-server admin:create admin admin@example.com

        # Non-interactive (reads password from stdin)
        echo "secretpass" | hop3-server admin:create admin admin@example.com --password-stdin

    The generated API token signs the CLI in:
        hop3 login --token <token> --url https://your-server.com
    """

    name = "admin:create"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("username", type=str, help="Username for the new admin")
        parser.add_argument("email", type=str, help="Email address for the new admin")
        parser.add_argument(
            "--password-stdin",
            action="store_true",
            dest="password_stdin",
            help="Read password from stdin (for automation)",
        )

    def run(self, username: str, email: str, *, password_stdin: bool = False) -> None:
        # Get password
        if password_stdin:
            password = sys.stdin.read().strip()
            if not password:
                print("Error: No password provided via stdin", file=sys.stderr)
                sys.exit(1)
        else:
            password = getpass.getpass("Password: ")
            password_confirm = getpass.getpass("Confirm password: ")
            if password != password_confirm:
                print("Error: Passwords do not match", file=sys.stderr)
                sys.exit(1)

        if not password:
            print("Error: Password cannot be empty", file=sys.stderr)
            sys.exit(1)

        with get_session() as db_session:
            user_repo = UserRepository(session=db_session)

            # Check if username already exists
            if user_repo.username_exists(username):
                print(f"Error: Username '{username}' already exists", file=sys.stderr)
                sys.exit(1)

            # Check if email already exists
            if user_repo.email_exists(email):
                print(f"Error: Email '{email}' already registered", file=sys.stderr)
                sys.exit(1)

            # Generate token BEFORE creating user - if this fails, we don't want
            # to leave a user in the database without being able to return a token
            token = create_token(username, scopes=["admin", "authenticated"])

            # Create user
            user = User(
                username=username,
                email=email,
                password_hash="",
                active=True,
                confirmed_at=datetime.now(timezone.utc),
                role=Role.ADMIN,
            )
            user.set_password(password)

            user_repo.add(user, auto_commit=True)

            print(f"Admin user '{username}' created successfully.")
            print()
            print("API Token (save this - it won't be shown again):")
            print(token)
            print()
            print("Quick login (replace SERVER_URL with your server address):")
            print(f'  hop3 login "SERVER_URL?token={token}"')
            print()
            print("Example for local development:")
            print(f'  hop3 login "http://localhost:8000?token={token}"')


@register
class AdminToken(Command):
    """
    Generate a new API token for an existing user.

    Usage:
        hop3-server admin:token <username>

    This command generates a new API token for an existing user.
    Useful for:
    - Users who lost their token
    - Setting up the CLI on a new machine
    - Token rotation

    Examples:
        hop3-server admin:token admin
    """

    name = "admin:token"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("username", type=str, help="Username to generate token for")

    def run(self, username: str) -> None:
        with get_session() as db_session:
            user_repo = UserRepository(session=db_session)

            user = user_repo.get_by_username(username)
            if not user:
                print(f"Error: User '{username}' not found", file=sys.stderr)
                sys.exit(1)

            if not user.active:
                print(
                    f"Error: User '{username}' is disabled. Enable the account first.",
                    file=sys.stderr,
                )
                sys.exit(1)

            if user.role is Role.MEMBER:
                print(f"Error: {member_token_refusal(username)}", file=sys.stderr)
                sys.exit(1)

            # Generate token with appropriate scopes
            scopes = ["authenticated"]
            if user.is_admin:
                scopes.append("admin")

            token = create_token(username, scopes=scopes)

            print(f"API token generated for user: {username}")
            print()
            print("Token:")
            print(token)
            print()
            print("Quick login (replace SERVER_URL with your server address):")
            print(f'  hop3 login "SERVER_URL?token={token}"')
            print()
            print("Example for local development:")
            print(f'  hop3 login "http://localhost:8000?token={token}"')


@register
class AdminList(Command):
    """
    List all users with their admin status.

    Usage:
        hop3-server admin:list

    Displays a table of all users showing:
    - Username
    - Email
    - Active status
    - Admin status
    - Login count
    """

    name = "admin:list"

    def run(self) -> None:
        with get_session() as db_session:
            user_repo = UserRepository(session=db_session)

            users = user_repo.list_all_ordered()

            if not users:
                print("No users found.")
                return

            # Print header
            print(
                f"{'Username':<20} {'Email':<30} {'Active':<8} {'Role':<10} {'Logins':<8}"
            )
            print("-" * 80)

            for user in users:
                active = "Yes" if user.active else "No"
                print(
                    f"{user.username:<20} {user.email:<30} {active:<8} {user.role:<10} {user.login_count:<8}"
                )

            print()
            print(f"Total users: {len(users)}")


@register
class AdminServerUrl(Command):
    """
    Print the server's public base URL, or nothing when it has none.

    Usage:
        hop3-server admin:server-url

    The address clients should use for everyday RPC: ``https://<ADMIN_DOMAIN>``.
    Only the server knows its own public identity — a client holds an SSH
    target, which says nothing about how nginx and TLS front the API.

    Prints nothing and exits 0 when no admin domain is configured. There is no
    HTTPS endpoint in that case, so the caller keeps tunnelling over SSH; the
    empty answer is the answer, not a failure. A server too old to have this
    command exits non-zero instead, which the caller reports differently.
    """

    name = "admin:server-url"

    def run(self) -> None:
        from hop3.config import config  # ruff:ignore[import-outside-top-level]

        if config.ADMIN_DOMAIN:
            print(f"https://{config.ADMIN_DOMAIN}")


@register
class AdminSshToken(Command):
    """
    Generate a token for SSH-based authentication.

    Usage:
        hop3-server admin:ssh-token

    This command is designed for automated SSH-based authentication.
    It requires no arguments - SSH access is the authentication.

    Behavior:
    - If no users exist: Creates a default admin user and returns token
    - If users exist: Returns a token for the first admin user

    This enables a simplified workflow where SSH access = admin access:
        ssh root@server hop3-server admin:ssh-token

    The CLI uses this internally for transparent authentication.
    """

    name = "admin:ssh-token"

    def run(self) -> None:
        import secrets  # ruff:ignore[import-outside-top-level]

        with get_session() as db_session:
            user_repo = UserRepository(session=db_session)

            # Try to find an existing admin user
            admin_user = self._find_admin_user(user_repo)

            if admin_user:
                # Generate token for existing admin
                scopes = ["authenticated", "admin"]
                token = create_token(admin_user.username, scopes=scopes)
                print(token)
                return

            # No admin exists - create default admin
            admin_user = self._create_default_admin(
                user_repo, secrets.token_urlsafe(32)
            )
            token = create_token(admin_user.username, scopes=["authenticated", "admin"])
            print(token)

    def _find_admin_user(self, user_repo: UserRepository) -> User | None:
        """Find an active admin, preferring one named 'admin'."""
        admin_by_name = user_repo.get_by_username("admin")
        if admin_by_name and admin_by_name.active and admin_by_name.is_admin:
            return admin_by_name

        for user in user_repo.list_all_ordered():
            if user.active and user.is_admin:
                return user

        return None

    def _create_default_admin(self, user_repo: UserRepository, password: str) -> User:
        """Create a default admin user."""
        # Create default admin user
        user = User(
            username="admin",
            email="admin@localhost",
            password_hash="",
            active=True,
            confirmed_at=datetime.now(timezone.utc),
            role=Role.ADMIN,
        )
        user.set_password(password)

        user_repo.add(user, auto_commit=True)

        # Log to stderr so it doesn't interfere with token output
        import sys  # ruff:ignore[import-outside-top-level]

        print("Created default admin user 'admin'", file=sys.stderr)

        return user


@register
class AdminResetPassword(Command):
    """
    Reset a user's password.

    Usage:
        hop3-server admin:reset-password <username> [--password-stdin]

    This command resets the password for an existing user.
    Useful for account recovery when the user has forgotten their password.

    Examples:
        # Interactive (prompts for password)
        hop3-server admin:reset-password admin

        # Non-interactive (reads password from stdin)
        echo "newpassword" | hop3-server admin:reset-password admin --password-stdin
    """

    name = "admin:reset-password"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("username", type=str, help="Username to reset password for")
        parser.add_argument(
            "--password-stdin",
            action="store_true",
            dest="password_stdin",
            help="Read password from stdin (for automation)",
        )

    def run(self, username: str, *, password_stdin: bool = False) -> None:
        # Get password
        if password_stdin:
            password = sys.stdin.read().strip()
            if not password:
                print("Error: No password provided via stdin", file=sys.stderr)
                sys.exit(1)
        else:
            password = getpass.getpass("New password: ")
            password_confirm = getpass.getpass("Confirm new password: ")
            if password != password_confirm:
                print("Error: Passwords do not match", file=sys.stderr)
                sys.exit(1)

        if not password:
            print("Error: Password cannot be empty", file=sys.stderr)
            sys.exit(1)

        with get_session() as db_session:
            user_repo = UserRepository(session=db_session)

            user = user_repo.get_by_username(username)
            if not user:
                print(f"Error: User '{username}' not found", file=sys.stderr)
                sys.exit(1)

            user.set_password(password)
            user_repo.update(user, auto_commit=True)

            print(f"Password reset successfully for user '{username}'")


@register
class AuthMagicLink(Command):
    """
    Generate a magic link for passwordless web login.

    Usage:
        hop3-server auth:magic-link [username]

    This command generates a short-lived, single-use token that can be used
    to log into the web dashboard without entering a password.

    The token:
    - Expires in 5 minutes
    - Can only be used once
    - Logs in as the specified user (default: admin)

    This is designed for SSH-based authentication workflows:
        ssh root@server hop3-server auth:magic-link

    The CLI uses this internally for `hop3 login --browser`.
    """

    name = "auth:magic-link"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "username",
            type=str,
            help="Username to generate magic link for (required, no default)",
        )

    def run(self, username: str) -> None:
        with get_session() as db_session:
            user_repo = UserRepository(session=db_session)

            user = user_repo.get_by_username(username)
            if not user:
                print(f"Error: User '{username}' not found", file=sys.stderr)
                sys.exit(1)

            if not user.active:
                print(f"Error: User '{username}' is disabled", file=sys.stderr)
                sys.exit(1)

            # Generate magic link token
            token = create_magic_token(username)

            # When the server has a public admin domain (nginx + TLS front the
            # dashboard there), emit the full URL — only the server knows its
            # own scheme/host. Without a domain, print the bare token and let
            # the CLI point at the app's HTTP port directly.
            from hop3.config import config  # ruff:ignore[import-outside-top-level]

            if config.ADMIN_DOMAIN:
                print(f"https://{config.ADMIN_DOMAIN}/auth/magic/{token}")
            else:
                print(token)
