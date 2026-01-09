# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Server-side CLI commands for admin user management.

These commands run directly on the server and provide bootstrap capabilities
for creating the first admin user without requiring HTTP authentication.

See ADR 014 for the design rationale.
"""

from __future__ import annotations

import getpass
import sys
from datetime import datetime, timezone

from hop3.lib.registry import register
from hop3.orm import Role, User
from hop3.server.lib.database import get_session
from hop3.server.security.tokens import create_token

from ._base import Command


@register
class Admin(Command):
    """Manage admin users and authentication tokens.

    Subcommands:
        admin:create         Create a new admin user
        admin:token          Generate a new token for an existing user
        admin:list           List all users
        admin:reset-password Reset a user's password

    Use 'hop3-server admin:<subcommand> --help' for details.
    """

    name = "admin"

    # No run method - Help class will show subcommands


@register
class AdminCreate(Command):
    """Create an admin user and display an API token.

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

    The generated API token should be saved and used to configure the CLI:
        hop3 settings set server https://your-server.com
        hop3 settings set token <token>
    """

    name = "admin:create"

    def add_arguments(self, parser):
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
            # Check if username already exists
            existing_user = db_session.query(User).filter_by(username=username).first()
            if existing_user:
                print(f"Error: Username '{username}' already exists", file=sys.stderr)
                sys.exit(1)

            # Check if email already exists
            existing_email = db_session.query(User).filter_by(email=email).first()
            if existing_email:
                print(f"Error: Email '{email}' already registered", file=sys.stderr)
                sys.exit(1)

            # Get or create admin role
            admin_role = db_session.query(Role).filter_by(name="admin").first()
            if not admin_role:
                admin_role = Role(name="admin", description="Administrator role")
                db_session.add(admin_role)
                db_session.flush()

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
            )
            user.set_password(password)
            user.roles.append(admin_role)

            db_session.add(user)
            db_session.commit()

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
    """Generate a new API token for an existing user.

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

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username to generate token for")

    def run(self, username: str) -> None:
        with get_session() as db_session:
            user = db_session.query(User).filter_by(username=username).first()
            if not user:
                print(f"Error: User '{username}' not found", file=sys.stderr)
                sys.exit(1)

            if not user.active:
                print(
                    f"Error: User '{username}' is disabled. Enable the account first.",
                    file=sys.stderr,
                )
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
    """List all users with their admin status.

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
            users = db_session.query(User).order_by(User.username).all()

            if not users:
                print("No users found.")
                return

            # Print header
            print(
                f"{'Username':<20} {'Email':<30} {'Active':<8} {'Admin':<8} {'Logins':<8}"
            )
            print("-" * 80)

            for user in users:
                is_admin = "Yes" if user.is_admin else "No"
                active = "Yes" if user.active else "No"
                print(
                    f"{user.username:<20} {user.email:<30} {active:<8} {is_admin:<8} {user.login_count:<8}"
                )

            print()
            print(f"Total users: {len(users)}")


@register
class AdminResetPassword(Command):
    """Reset a user's password.

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

    def add_arguments(self, parser):
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
            user = db_session.query(User).filter_by(username=username).first()
            if not user:
                print(f"Error: User '{username}' not found", file=sys.stderr)
                sys.exit(1)

            user.set_password(password)
            db_session.commit()

            print(f"Password reset successfully for user '{username}'")
