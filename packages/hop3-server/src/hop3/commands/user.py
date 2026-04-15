# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for user management (ADR 036 D3: flattened from admin:user:*)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar

from hop3.lib.registry import register
from hop3.orm import User

# Repositories are runtime imports for Dishka DI (not just type hints)
from hop3.orm.repositories import RoleRepository, UserRepository  # noqa: TC001
from hop3.orm.security import Role
from hop3.server.security.tokens import create_token

from ._base import Command
from ._response import error, text


def require_admin(username: str, user_repo: UserRepository) -> list[dict] | None:
    """Check if the authenticated user is an admin.

    Args:
        username: The authenticated username
        user_repo: User repository

    Returns:
        Error response if not admin, None if admin
    """
    if not username:
        return [
            error("Authentication required. Use 'hop3 auth login' to authenticate.")
        ]

    user = user_repo.get_by_username(username)
    if not user or not user.is_admin:
        return [error("Admin privileges required")]

    return None


@register
@dataclass(frozen=True)
class UserAddCmd(Command):
    """Create a new user account.

    Usage: hop3 user add <username> <email> <password> [--admin]

    Options:
        --admin: Grant admin privileges to the new user

    Examples:
        hop3 user add john john@example.com secret123
        hop3 user add admin admin@example.com admin123 --admin
    """

    user_repo: UserRepository
    role_repo: RoleRepository
    name: ClassVar[tuple[str, ...]] = ("user", "add")
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        email: str = "",
        password: str = "",
        *args,
    ):
        """Create a new user account.

        Args:
            authenticated_username: The authenticated user
            username: Username for the new user
            email: Email for the new user
            password: Password for the new user
            *args: Additional arguments (--admin flag)

        Returns:
            Success message or error
        """
        # Check admin privileges
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not username or not email or not password:
            return [
                error(
                    "Usage: hop3 user add <username> <email> <password> [--admin]"
                )
            ]

        # Check if username already exists
        if self.user_repo.username_exists(username):
            return [error(f"Username '{username}' already exists")]

        # Check if email already exists
        if self.user_repo.email_exists(email):
            return [error(f"Email '{email}' already registered")]

        # Check for --admin flag
        is_admin = "--admin" in args

        # Create new user
        user = User(username=username, email=email, password_hash="")
        user.set_password(password)
        user.active = True
        user.confirmed_at = datetime.now(timezone.utc)

        # Grant admin role if requested
        if is_admin:
            admin_role = self.role_repo.get_admin_role()
            if not admin_role:
                # Create admin role if it doesn't exist
                admin_role = Role(name="admin", description="Administrator role")
                self.role_repo.add(admin_role)
            user.roles.append(admin_role)

        self.user_repo.add(user, auto_commit=True)

        response = [
            text(f"User '{username}' created successfully!"),
            text(f"Email: {email}"),
            text(f"Active: {user.active}"),
        ]

        if is_admin:
            response.append(text("Admin: Yes"))

        return response


@register
@dataclass(frozen=True)
class UserRemoveCmd(Command):
    """Remove a user account.

    Usage: hop3 user remove <username>

    Warning: This permanently deletes the user account.

    Examples:
        hop3 user remove john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "remove")
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Remove a user account.

        Args:
            authenticated_username: The authenticated user
            username: Username to remove

        Returns:
            Success message or error
        """
        # Check admin privileges
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not username:
            return [error("Usage: hop3 user remove <username>")]

        # Prevent self-deletion
        if username == authenticated_username:
            return [error("Cannot remove your own account")]

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        # Delete the user (pass id, not the object)
        self.user_repo.delete(user.id, auto_commit=True)

        return [text(f"User '{username}' removed successfully")]


@register
@dataclass(frozen=True)
class UserListCmd(Command):
    """List all user accounts.

    Usage: hop3 user list

    Examples:
        hop3 user list
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "list")
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", *args):
        """List all user accounts.

        Args:
            authenticated_username: The authenticated user

        Returns:
            List of users or error
        """
        # Check admin privileges
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        # Get all users
        users = self.user_repo.list_all_ordered()

        if not users:
            return [text("No users found")]

        response = [
            text("Users"),
            text("=" * 80),
            text(
                f"{'Username':<20} {'Email':<30} {'Active':<8} {'Admin':<8} {'Logins':<8}"
            ),
            text("-" * 80),
        ]

        for user in users:
            is_admin = "Yes" if user.is_admin else "No"
            active = "Yes" if user.active else "No"
            response.append(
                text(
                    f"{user.username:<20} {user.email:<30} {active:<8} {is_admin:<8} {user.login_count:<8}"
                )
            )

        response.append(text(""))
        response.append(text(f"Total users: {len(users)}"))

        return response


@register
@dataclass(frozen=True)
class UserEnableCmd(Command):
    """Enable a disabled user account.

    Usage: hop3 user enable <username>

    Examples:
        hop3 user enable john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "enable")
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Enable a user account.

        Args:
            authenticated_username: The authenticated user
            username: Username to enable

        Returns:
            Success message or error
        """
        # Check admin privileges
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not username:
            return [error("Usage: hop3 user enable <username>")]

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        if user.active:
            return [text(f"User '{username}' is already enabled")]

        # Enable the user
        user.active = True
        self.user_repo.update(user, auto_commit=True)

        return [text(f"User '{username}' enabled successfully")]


@register
@dataclass(frozen=True)
class UserDisableCmd(Command):
    """Disable a user account.

    Usage: hop3 user disable <username>

    Examples:
        hop3 user disable john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "disable")
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Disable a user account.

        Args:
            authenticated_username: The authenticated user
            username: Username to disable

        Returns:
            Success message or error
        """
        # Check admin privileges
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not username:
            return [error("Usage: hop3 user disable <username>")]

        # Prevent self-disable
        if username == authenticated_username:
            return [error("Cannot disable your own account")]

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        if not user.active:
            return [text(f"User '{username}' is already disabled")]

        # Disable the user
        user.active = False
        self.user_repo.update(user, auto_commit=True)

        return [text(f"User '{username}' disabled successfully")]


@register
@dataclass(frozen=True)
class UserGrantAdminCmd(Command):
    """Grant admin privileges to a user.

    Usage: hop3 user grant-admin <username>

    Examples:
        hop3 user grant-admin john
    """

    user_repo: UserRepository
    role_repo: RoleRepository
    name: ClassVar[tuple[str, ...]] = ("user", "grant-admin")
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Grant admin privileges to a user.

        Args:
            authenticated_username: The authenticated user
            username: Username to grant admin privileges to

        Returns:
            Success message or error
        """
        # Check admin privileges
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not username:
            return [error("Usage: hop3 user grant-admin <username>")]

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        if user.is_admin:
            return [text(f"User '{username}' already has admin privileges")]

        # Get or create admin role
        admin_role = self.role_repo.get_admin_role()
        if not admin_role:
            admin_role = Role(name="admin", description="Administrator role")
            self.role_repo.add(admin_role)

        # Grant admin role
        user.roles.append(admin_role)
        self.user_repo.update(user, auto_commit=True)

        return [text(f"Admin privileges granted to user '{username}' successfully")]


@register
@dataclass(frozen=True)
class UserRevokeAdminCmd(Command):
    """Revoke admin privileges from a user.

    Usage: hop3 user revoke-admin <username>

    Examples:
        hop3 user revoke-admin john
    """

    user_repo: UserRepository
    role_repo: RoleRepository
    name: ClassVar[tuple[str, ...]] = ("user", "revoke-admin")
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Revoke admin privileges from a user.

        Args:
            authenticated_username: The authenticated user
            username: Username to revoke admin privileges from

        Returns:
            Success message or error
        """
        # Check admin privileges
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not username:
            return [error("Usage: hop3 user revoke-admin <username>")]

        # Prevent self-revocation
        if username == authenticated_username:
            return [error("Cannot revoke admin privileges from yourself")]

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        if not user.is_admin:
            return [text(f"User '{username}' does not have admin privileges")]

        # Get admin role
        admin_role = self.role_repo.get_admin_role()
        if admin_role and admin_role in user.roles:
            user.roles.remove(admin_role)
            self.user_repo.update(user, auto_commit=True)

        return [text(f"Admin privileges revoked from user '{username}' successfully")]


@register
@dataclass(frozen=True)
class UserSetPasswordCmd(Command):
    """Reset a user's password.

    Usage: hop3 user set-password <username> <new_password>

    Examples:
        hop3 user set-password john newpassword123
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "set-password")
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        new_password: str = "",
        *args,
    ):
        """Reset a user's password.

        Args:
            authenticated_username: The authenticated user
            username: Username whose password to reset
            new_password: New password for the user

        Returns:
            Success message or error
        """
        # Check admin privileges
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not username or not new_password:
            return [
                error("Usage: hop3 user set-password <username> <new_password>")
            ]

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        # Set new password
        user.set_password(new_password)
        self.user_repo.update(user, auto_commit=True)

        return [text(f"Password reset successfully for user '{username}'")]


@register
@dataclass(frozen=True)
class UserShowCmd(Command):
    """Display detailed information about a user.

    Usage: hop3 user info <username>

    Examples:
        hop3 user info john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "show")
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Display detailed information about a user.

        Args:
            authenticated_username: The authenticated user
            username: Username to get information about

        Returns:
            User information or error
        """
        # Check admin privileges
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not username:
            return [error("Usage: hop3 user info <username>")]

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        roles = ", ".join(role.name for role in user.roles) if user.roles else "None"

        return [
            text("User Information"),
            text("=" * 40),
            text(f"Username: {user.username}"),
            text(f"Email: {user.email}"),
            text(f"Active: {user.active}"),
            text(f"Admin: {user.is_admin}"),
            text(f"Roles: {roles}"),
            text(f"Login count: {user.login_count}"),
            text(f"Current login: {user.current_login_at or 'Never'}"),
            text(f"Last login: {user.last_login_at or 'Never'}"),
            text(f"Confirmed at: {user.confirmed_at or 'Not confirmed'}"),
            text(f"Created: {user.created_at}"),
            text(f"Updated: {user.updated_at}"),
        ]


@register
@dataclass(frozen=True)
class UserGenerateTokenCmd(Command):
    """Generate a new API token for a user (bootstrap helper).

    Usage: hop3 user generate-token <username>

    This is useful for bootstrapping or when a user has lost their token.

    Examples:
        hop3 user generate-token john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "generate-token")
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Generate a new API token for a user.

        Args:
            authenticated_username: The authenticated user
            username: Username to generate token for

        Returns:
            Token or error
        """
        # Check admin privileges
        if admin_error := require_admin(authenticated_username, self.user_repo):
            return admin_error

        if not username:
            return [error("Usage: hop3 user generate-token <username>")]

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        if not user.active:
            return [error(f"User '{username}' is disabled. Enable the account first.")]

        # Generate token
        scopes = ["authenticated"]
        if user.is_admin:
            scopes.append("admin")

        token = create_token(username, scopes=scopes)

        return [
            text(f"API token generated for user: {username}"),
            text(""),
            text("Token:"),
            text(token),
            text(""),
            text("The user should save this to their config file:"),
            text(f'api_token = "{token}"'),
        ]
