# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for user management (ADR 036 D3: flattened from admin:user:*)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar

from hop3.core.roles import Role
from hop3.lib.registry import register
from hop3.orm import User

# Repositories are runtime imports for Dishka DI (not just type hints)
from hop3.orm.repositories import (  # ruff:ignore[typing-only-first-party-import]
    UserRepository,
)
from hop3.server.security.tokens import create_token

from ._base import Command, NamespaceCommand
from ._response import error, summary, text
from .auth import member_token_refusal


def _requested_role(args: tuple[str, ...]) -> Role:
    """
    The role a ``user add`` asks for: ``--role NAME``, ``--admin``, or ``member``.

    Raises ValueError, with a message for the user, on an unknown or missing name.
    """
    if "--admin" in args:
        return Role.ADMIN
    if "--role" not in args:
        return Role.MEMBER
    index = args.index("--role")
    if index + 1 >= len(args):
        msg = "--role needs a value: " + ", ".join(role.value for role in Role)
        raise ValueError(msg)
    return Role.parse(args[index + 1])


def _set_role(
    user_repo: UserRepository,
    authenticated_username: str,
    username: str,
    role: Role,
) -> list[dict]:
    """
    Give ``username`` the server role ``role``, on behalf of an admin.

    An admin cannot change their own role. Every other change is made by an
    active admin who keeps that role, so the server can never be left without
    an admin through this path (ADR 061 §2).
    """
    user = user_repo.get_by_username(username)
    if not user:
        return [error(f"User '{username}' not found")]

    if user.role is role:
        return [text(f"User '{username}' is already {role}")]

    if username == authenticated_username:
        return [
            error(
                "Cannot change your own role: another admin must, so the server "
                "is never left without one"
            )
        ]

    previous = user.role
    user.role = role
    user_repo.update(user, auto_commit=True)

    return [
        text(f"User '{username}' is now {role} (was {previous})"),
        summary(f"set '{username}' to {role}."),
    ]


@register
@dataclass(frozen=True)
class UserCmd(NamespaceCommand):
    """
    Manage user accounts.

    Examples:
        hop3 user list                 # List all user accounts
        hop3 user add alice a@ex.com   # Register a new user
        hop3 user show alice           # Show details for a user
    """

    name: ClassVar[tuple[str, ...]] = ("user",)
    min_role: ClassVar[Role] = Role.ADMIN


@register
@dataclass(frozen=True)
class UserAddCmd(Command):
    """
    Register a new user account.

    Usage: hop3 user add <username> <email> [password] [--role ROLE | --admin]
                                            (--password-file <path> | --stdin)

    Options:
        --role ROLE           The account's role: member (the default), viewer,
                              deployer or admin
        --admin               Same as --role admin
        --password-file PATH  Read password from PATH (use '-' for stdin)
        --stdin               Read password from stdin

    Examples:
        # Recommended (password not in shell history / ps output)
        hop3 user add admin admin@example.com --password-file ./pw.txt --admin
        echo "$PW" | hop3 user add john john@example.com --stdin --role deployer

        # Direct positional (discouraged: leaks via shell history and ps)
        hop3 user add john john@example.com secret123
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "add")
    min_role: ClassVar[Role] = Role.ADMIN
    # `auth register` was a duplicate of this command (ADR 036 P2.1) — kept as a
    # back-compat alias so `hop3 auth register u e p` still works.
    aliases: ClassVar[list[tuple[str, ...]]] = [("auth", "register")]
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        email: str = "",
        password: str = "",
        /,
        *args: str,
        **kwargs: object,
    ) -> list[dict]:
        """
        Create a new user account.

        Args:
            authenticated_username: The authenticated user
            username: Username for the new user
            email: Email for the new user
            password: Password for the new user
            *args: Additional arguments (--role ROLE, --admin)

        Returns:
            Success message or error
        """
        if not username or not email or not password:
            raise self.usage_error()

        try:
            role = _requested_role(args)
        except ValueError as e:
            return [error(str(e))]

        # Check if username already exists
        if self.user_repo.username_exists(username):
            return [error(f"Username '{username}' already exists")]

        # Check if email already exists
        if self.user_repo.email_exists(email):
            return [error(f"Email '{email}' already registered")]

        # Create new user
        user = User(username=username, email=email, password_hash="", role=role)
        user.set_password(password)
        user.active = True
        user.confirmed_at = datetime.now(timezone.utc)

        self.user_repo.add(user, auto_commit=True)

        response = [
            text(f"User '{username}' created successfully!"),
            text(f"Email: {email}"),
            text(f"Active: {user.active}"),
            text(f"Role: {role}"),
        ]

        # A deployer's builds run recipe code with the control plane's own
        # privileges until builds drop to the app user (ADR 061 §6, ADR 055),
        # so the role protects nothing an admin credential would not. Say so
        # where the account is created, rather than let "deployer" imply a
        # confinement the platform doesn't provide yet.
        if role is Role.DEPLOYER:
            response.append(
                text(
                    "Note: a deployer's builds run with the control plane's own "
                    "privileges, so treat this account as an administrator "
                    "credential. See https://hop3.cloud/guides/security/"
                )
            )

        response.append(summary(f"added user '{username}' ({role})."))
        return response


@register
@dataclass(frozen=True)
class UserRemoveCmd(Command):
    """
    Remove a user account.

    Usage: hop3 user remove <username>

    Warning: This permanently deletes the user account.

    Examples:
        hop3 user remove john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "remove")
    min_role: ClassVar[Role] = Role.ADMIN
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        /,
        *args: str,
        **kwargs: object,
    ) -> list[dict]:
        """
        Remove a user account.

        Args:
            authenticated_username: The authenticated user
            username: Username to remove

        Returns:
            Success message or error
        """
        if not username:
            raise self.usage_error()

        # Prevent self-deletion
        if username == authenticated_username:
            return [error("Cannot remove your own account")]

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        # Delete the user (pass id, not the object)
        self.user_repo.delete(user.id, auto_commit=True)

        return [
            text(f"User '{username}' removed successfully"),
            summary(f"removed user '{username}'."),
        ]


@register
@dataclass(frozen=True)
class UserListCmd(Command):
    """
    List all user accounts.

    Usage: hop3 user list

    Examples:
        hop3 user list
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "list")
    min_role: ClassVar[Role] = Role.ADMIN
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self, authenticated_username: str = "", /, *args: str, **kwargs: object
    ) -> list[dict]:
        """
        List all user accounts.

        Args:
            authenticated_username: The authenticated user

        Returns:
            List of users or error
        """
        # Get all users
        users = self.user_repo.list_all_ordered()

        if not users:
            return [text("No users found")]

        response = [
            text("Users"),
            text("=" * 80),
            text(
                f"{'Username':<20} {'Email':<30} {'Active':<8} {'Role':<10} {'Logins':<8}"
            ),
            text("-" * 80),
        ]

        for user in users:
            active = "Yes" if user.active else "No"
            response.append(
                text(
                    f"{user.username:<20} {user.email:<30} {active:<8} {user.role:<10} {user.login_count:<8}"
                )
            )

        response.append(text(""))
        response.append(text(f"Total users: {len(users)}"))

        return response


@register
@dataclass(frozen=True)
class UserEnableCmd(Command):
    """
    Enable a disabled user account.

    Usage: hop3 user enable <username>

    Examples:
        hop3 user enable john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "enable")
    min_role: ClassVar[Role] = Role.ADMIN
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        /,
        *args: str,
        **kwargs: object,
    ) -> list[dict]:
        """
        Enable a user account.

        Args:
            authenticated_username: The authenticated user
            username: Username to enable

        Returns:
            Success message or error
        """
        if not username:
            raise self.usage_error()

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        if user.active:
            return [text(f"User '{username}' is already enabled")]

        # Enable the user
        user.active = True
        self.user_repo.update(user, auto_commit=True)

        return [
            text(f"User '{username}' enabled successfully"),
            summary(f"enabled user '{username}'."),
        ]


@register
@dataclass(frozen=True)
class UserDisableCmd(Command):
    """
    Disable a user account.

    Usage: hop3 user disable <username>

    Examples:
        hop3 user disable john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "disable")
    min_role: ClassVar[Role] = Role.ADMIN
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        /,
        *args: str,
        **kwargs: object,
    ) -> list[dict]:
        """
        Disable a user account.

        Args:
            authenticated_username: The authenticated user
            username: Username to disable

        Returns:
            Success message or error
        """
        if not username:
            raise self.usage_error()

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

        return [
            text(f"User '{username}' disabled successfully"),
            summary(f"disabled user '{username}'."),
        ]


@register
@dataclass(frozen=True)
class UserSetRoleCmd(Command):
    """
    Set a user's role.

    Usage: hop3 user set-role <username> <role>

    The roles, lowest first: member (signs in, no control-plane access), viewer
    (reads app state), deployer (runs apps), admin (everything, users included).
    An admin cannot change their own role.

    Examples:
        hop3 user set-role john deployer
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "set-role")
    min_role: ClassVar[Role] = Role.ADMIN
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        role: str = "",
        /,
        *args: str,
        **kwargs: object,
    ) -> list[dict]:
        """Give ``username`` the role ``role``."""
        if not username or not role:
            raise self.usage_error()
        try:
            parsed = Role.parse(role)
        except ValueError as e:
            return [error(str(e))]
        return _set_role(self.user_repo, authenticated_username, username, parsed)


@register
@dataclass(frozen=True)
class UserGrantAdminCmd(Command):
    """
    Make a user an admin. Same as ``hop3 user set-role <username> admin``.

    Usage: hop3 user grant-admin <username>

    Examples:
        hop3 user grant-admin john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "grant-admin")
    min_role: ClassVar[Role] = Role.ADMIN
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        /,
        *args: str,
        **kwargs: object,
    ) -> list[dict]:
        """Give ``username`` the ``admin`` role."""
        if not username:
            raise self.usage_error()
        return _set_role(self.user_repo, authenticated_username, username, Role.ADMIN)


@register
@dataclass(frozen=True)
class UserRevokeAdminCmd(Command):
    """
    Take the admin role from a user, leaving them a deployer.

    A deployer keeps what every non-admin account could do before roles
    existed: run and configure every app, without managing users. Use
    ``hop3 user set-role`` for any other role.

    Usage: hop3 user revoke-admin <username>

    Examples:
        hop3 user revoke-admin john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "revoke-admin")
    min_role: ClassVar[Role] = Role.ADMIN
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        /,
        *args: str,
        **kwargs: object,
    ) -> list[dict]:
        """Move ``username`` from ``admin`` to ``deployer``."""
        if not username:
            raise self.usage_error()
        user = self.user_repo.get_by_username(username)
        if user and not user.is_admin:
            return [text(f"User '{username}' is not an admin (role: {user.role})")]
        return _set_role(
            self.user_repo, authenticated_username, username, Role.DEPLOYER
        )


@register
@dataclass(frozen=True)
class UserSetPasswordCmd(Command):
    """
    Reset a user's password.

    Usage: hop3 user set-password <username> [new_password]
                                  (--password-file <path> | --stdin)

    Options:
        --password-file PATH  Read password from PATH (use '-' for stdin)
        --stdin               Read password from stdin

    Examples:
        # Recommended
        hop3 user set-password john --password-file ./newpw.txt
        echo "$PW" | hop3 user set-password john --stdin

        # Direct positional (discouraged: leaks via shell history and ps)
        hop3 user set-password john newpassword123
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "set-password")
    min_role: ClassVar[Role] = Role.ADMIN
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        new_password: str = "",
        /,
        *args: str,
        **kwargs: object,
    ) -> list[dict]:
        """
        Reset a user's password.

        Args:
            authenticated_username: The authenticated user
            username: Username whose password to reset
            new_password: New password for the user

        Returns:
            Success message or error
        """
        if not username or not new_password:
            raise self.usage_error()

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        # Set new password
        user.set_password(new_password)
        self.user_repo.update(user, auto_commit=True)

        return [
            text(f"Password reset successfully for user '{username}'"),
            summary(f"reset password for '{username}'."),
        ]


@register
@dataclass(frozen=True)
class UserShowCmd(Command):
    """
    Show detailed information about a user.

    Usage: hop3 user show <username>

    Examples:
        hop3 user show john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "show")
    min_role: ClassVar[Role] = Role.ADMIN
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        /,
        *args: str,
        **kwargs: object,
    ) -> list[dict]:
        """
        Display detailed information about a user.

        Args:
            authenticated_username: The authenticated user
            username: Username to get information about

        Returns:
            User information or error
        """
        if not username:
            raise self.usage_error()

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        return [
            text("User Information"),
            text("=" * 40),
            text(f"Username: {user.username}"),
            text(f"Email: {user.email}"),
            text(f"Active: {user.active}"),
            text(f"Role: {user.role}"),
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
    """
    Generate a new API token for a user (bootstrap helper).

    Usage: hop3 user generate-token <username>

    This is useful for bootstrapping or when a user has lost their token.

    Examples:
        hop3 user generate-token john
    """

    user_repo: UserRepository
    name: ClassVar[tuple[str, ...]] = ("user", "generate-token")
    min_role: ClassVar[Role] = Role.ADMIN
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(
        self,
        authenticated_username: str = "",
        username: str = "",
        /,
        *args: str,
        **kwargs: object,
    ) -> list[dict]:
        """
        Generate a new API token for a user.

        Args:
            authenticated_username: The authenticated user
            username: Username to generate token for

        Returns:
            Token or error
        """
        if not username:
            raise self.usage_error()

        # Find the user
        user = self.user_repo.get_by_username(username)
        if not user:
            return [error(f"User '{username}' not found")]

        if not user.active:
            return [error(f"User '{username}' is disabled. Enable the account first.")]

        if user.role is Role.MEMBER:
            return [error(member_token_refusal(username))]

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
