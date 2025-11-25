# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for administrative user management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from hop3.lib.registry import register
from hop3.orm import User
from hop3.orm.security import Role
from hop3.server.security.tokens import create_token

from ._base import Command

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def require_admin(username: str, db_session: Session) -> list[dict] | None:
    """Check if the authenticated user is an admin.

    Args:
        username: The authenticated username
        db_session: Database session

    Returns:
        Error response if not admin, None if admin
    """
    if not username:
        return [
            {
                "t": "error",
                "text": "Authentication required. Use 'hop3 auth:login' to authenticate.",
            }
        ]

    user = db_session.query(User).filter_by(username=username).first()
    if not user or not user.is_admin:
        return [{"t": "error", "text": "Admin privileges required"}]

    return None


@register
@dataclass(frozen=True)
class AdminCmd(Command):
    """Administrative commands."""

    name: ClassVar[str] = "admin"


@register
@dataclass(frozen=True)
class AdminUserAddCmd(Command):
    """Create a new user account.

    Usage: hop3 admin:user:add <username> <email> <password> [--admin]

    Options:
        --admin: Grant admin privileges to the new user

    Examples:
        hop3 admin:user:add john john@example.com secret123
        hop3 admin:user:add admin admin@example.com admin123 --admin
    """

    db_session: Session
    name: ClassVar[str] = "admin:user:add"
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
            authenticated_username: The authenticated admin user
            username: Username for the new user
            email: Email for the new user
            password: Password for the new user
            *args: Additional arguments (--admin flag)

        Returns:
            Success message or error
        """
        # Check admin privileges
        if error := require_admin(authenticated_username, self.db_session):
            return error

        if not username or not email or not password:
            return [
                {
                    "t": "error",
                    "text": "Usage: hop3 admin:user:add <username> <email> <password> [--admin]",
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

        # Check for --admin flag
        is_admin = "--admin" in args

        # Create new user
        user = User(username=username, email=email, password_hash="")
        user.set_password(password)
        user.active = True
        user.confirmed_at = datetime.now(timezone.utc)

        # Grant admin role if requested
        if is_admin:
            admin_role = self.db_session.query(Role).filter_by(name="admin").first()
            if not admin_role:
                # Create admin role if it doesn't exist
                admin_role = Role(name="admin", description="Administrator role")
                self.db_session.add(admin_role)
                self.db_session.flush()
            user.roles.append(admin_role)

        self.db_session.add(user)
        self.db_session.commit()

        response = [
            {"t": "text", "text": f"User '{username}' created successfully!"},
            {"t": "text", "text": f"Email: {email}"},
            {"t": "text", "text": f"Active: {user.active}"},
        ]

        if is_admin:
            response.append({"t": "text", "text": "Admin: Yes"})

        return response


@register
@dataclass(frozen=True)
class AdminUserRemoveCmd(Command):
    """Remove a user account.

    Usage: hop3 admin:user:remove <username>

    Warning: This permanently deletes the user account.

    Examples:
        hop3 admin:user:remove john
    """

    db_session: Session
    name: ClassVar[str] = "admin:user:remove"
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Remove a user account.

        Args:
            authenticated_username: The authenticated admin user
            username: Username to remove

        Returns:
            Success message or error
        """
        # Check admin privileges
        if error := require_admin(authenticated_username, self.db_session):
            return error

        if not username:
            return [{"t": "error", "text": "Usage: hop3 admin:user:remove <username>"}]

        # Prevent self-deletion
        if username == authenticated_username:
            return [{"t": "error", "text": "Cannot remove your own account"}]

        # Find the user
        user = self.db_session.query(User).filter_by(username=username).first()
        if not user:
            return [{"t": "error", "text": f"User '{username}' not found"}]

        # Delete the user
        self.db_session.delete(user)
        self.db_session.commit()

        return [{"t": "text", "text": f"User '{username}' removed successfully"}]


@register
@dataclass(frozen=True)
class AdminUserListCmd(Command):
    """List all user accounts.

    Usage: hop3 admin:user:list

    Examples:
        hop3 admin:user:list
    """

    db_session: Session
    name: ClassVar[str] = "admin:user:list"
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", *args):
        """List all user accounts.

        Args:
            authenticated_username: The authenticated admin user

        Returns:
            List of users or error
        """
        # Check admin privileges
        if error := require_admin(authenticated_username, self.db_session):
            return error

        # Get all users
        users = self.db_session.query(User).order_by(User.username).all()

        if not users:
            return [{"t": "text", "text": "No users found"}]

        response = [
            {"t": "text", "text": "Users"},
            {"t": "text", "text": "=" * 80},
            {
                "t": "text",
                "text": f"{'Username':<20} {'Email':<30} {'Active':<8} {'Admin':<8} {'Logins':<8}",
            },
            {"t": "text", "text": "-" * 80},
        ]

        for user in users:
            is_admin = "Yes" if user.is_admin else "No"
            active = "Yes" if user.active else "No"
            response.append({
                "t": "text",
                "text": f"{user.username:<20} {user.email:<30} {active:<8} {is_admin:<8} {user.login_count:<8}",
            })

        response.append({"t": "text", "text": ""})
        response.append({"t": "text", "text": f"Total users: {len(users)}"})

        return response


@register
@dataclass(frozen=True)
class AdminUserEnableCmd(Command):
    """Enable a disabled user account.

    Usage: hop3 admin:user:enable <username>

    Examples:
        hop3 admin:user:enable john
    """

    db_session: Session
    name: ClassVar[str] = "admin:user:enable"
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Enable a user account.

        Args:
            authenticated_username: The authenticated admin user
            username: Username to enable

        Returns:
            Success message or error
        """
        # Check admin privileges
        if error := require_admin(authenticated_username, self.db_session):
            return error

        if not username:
            return [{"t": "error", "text": "Usage: hop3 admin:user:enable <username>"}]

        # Find the user
        user = self.db_session.query(User).filter_by(username=username).first()
        if not user:
            return [{"t": "error", "text": f"User '{username}' not found"}]

        if user.active:
            return [{"t": "text", "text": f"User '{username}' is already enabled"}]

        # Enable the user
        user.active = True
        self.db_session.commit()

        return [{"t": "text", "text": f"User '{username}' enabled successfully"}]


@register
@dataclass(frozen=True)
class AdminUserDisableCmd(Command):
    """Disable a user account.

    Usage: hop3 admin:user:disable <username>

    Examples:
        hop3 admin:user:disable john
    """

    db_session: Session
    name: ClassVar[str] = "admin:user:disable"
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Disable a user account.

        Args:
            authenticated_username: The authenticated admin user
            username: Username to disable

        Returns:
            Success message or error
        """
        # Check admin privileges
        if error := require_admin(authenticated_username, self.db_session):
            return error

        if not username:
            return [{"t": "error", "text": "Usage: hop3 admin:user:disable <username>"}]

        # Prevent self-disable
        if username == authenticated_username:
            return [{"t": "error", "text": "Cannot disable your own account"}]

        # Find the user
        user = self.db_session.query(User).filter_by(username=username).first()
        if not user:
            return [{"t": "error", "text": f"User '{username}' not found"}]

        if not user.active:
            return [{"t": "text", "text": f"User '{username}' is already disabled"}]

        # Disable the user
        user.active = False
        self.db_session.commit()

        return [{"t": "text", "text": f"User '{username}' disabled successfully"}]


@register
@dataclass(frozen=True)
class AdminUserGrantAdminCmd(Command):
    """Grant admin privileges to a user.

    Usage: hop3 admin:user:grant-admin <username>

    Examples:
        hop3 admin:user:grant-admin john
    """

    db_session: Session
    name: ClassVar[str] = "admin:user:grant-admin"
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Grant admin privileges to a user.

        Args:
            authenticated_username: The authenticated admin user
            username: Username to grant admin privileges to

        Returns:
            Success message or error
        """
        # Check admin privileges
        if error := require_admin(authenticated_username, self.db_session):
            return error

        if not username:
            return [
                {
                    "t": "error",
                    "text": "Usage: hop3 admin:user:grant-admin <username>",
                }
            ]

        # Find the user
        user = self.db_session.query(User).filter_by(username=username).first()
        if not user:
            return [{"t": "error", "text": f"User '{username}' not found"}]

        if user.is_admin:
            return [
                {"t": "text", "text": f"User '{username}' already has admin privileges"}
            ]

        # Get or create admin role
        admin_role = self.db_session.query(Role).filter_by(name="admin").first()
        if not admin_role:
            admin_role = Role(name="admin", description="Administrator role")
            self.db_session.add(admin_role)
            self.db_session.flush()

        # Grant admin role
        user.roles.append(admin_role)
        self.db_session.commit()

        return [
            {
                "t": "text",
                "text": f"Admin privileges granted to user '{username}' successfully",
            }
        ]


@register
@dataclass(frozen=True)
class AdminUserRevokeAdminCmd(Command):
    """Revoke admin privileges from a user.

    Usage: hop3 admin:user:revoke-admin <username>

    Examples:
        hop3 admin:user:revoke-admin john
    """

    db_session: Session
    name: ClassVar[str] = "admin:user:revoke-admin"
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Revoke admin privileges from a user.

        Args:
            authenticated_username: The authenticated admin user
            username: Username to revoke admin privileges from

        Returns:
            Success message or error
        """
        # Check admin privileges
        if error := require_admin(authenticated_username, self.db_session):
            return error

        if not username:
            return [
                {
                    "t": "error",
                    "text": "Usage: hop3 admin:user:revoke-admin <username>",
                }
            ]

        # Prevent self-revocation
        if username == authenticated_username:
            return [
                {"t": "error", "text": "Cannot revoke admin privileges from yourself"}
            ]

        # Find the user
        user = self.db_session.query(User).filter_by(username=username).first()
        if not user:
            return [{"t": "error", "text": f"User '{username}' not found"}]

        if not user.is_admin:
            return [
                {
                    "t": "text",
                    "text": f"User '{username}' does not have admin privileges",
                }
            ]

        # Get admin role
        admin_role = self.db_session.query(Role).filter_by(name="admin").first()
        if admin_role and admin_role in user.roles:
            user.roles.remove(admin_role)
            self.db_session.commit()

        return [
            {
                "t": "text",
                "text": f"Admin privileges revoked from user '{username}' successfully",
            }
        ]


@register
@dataclass(frozen=True)
class AdminUserSetPasswordCmd(Command):
    """Reset a user's password.

    Usage: hop3 admin:user:set-password <username> <new_password>

    Examples:
        hop3 admin:user:set-password john newpassword123
    """

    db_session: Session
    name: ClassVar[str] = "admin:user:set-password"
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
            authenticated_username: The authenticated admin user
            username: Username whose password to reset
            new_password: New password for the user

        Returns:
            Success message or error
        """
        # Check admin privileges
        if error := require_admin(authenticated_username, self.db_session):
            return error

        if not username or not new_password:
            return [
                {
                    "t": "error",
                    "text": "Usage: hop3 admin:user:set-password <username> <new_password>",
                }
            ]

        # Find the user
        user = self.db_session.query(User).filter_by(username=username).first()
        if not user:
            return [{"t": "error", "text": f"User '{username}' not found"}]

        # Set new password
        user.set_password(new_password)
        self.db_session.commit()

        return [
            {"t": "text", "text": f"Password reset successfully for user '{username}'"}
        ]


@register
@dataclass(frozen=True)
class AdminUserInfoCmd(Command):
    """Display detailed information about a user.

    Usage: hop3 admin:user:info <username>

    Examples:
        hop3 admin:user:info john
    """

    db_session: Session
    name: ClassVar[str] = "admin:user:info"
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Display detailed information about a user.

        Args:
            authenticated_username: The authenticated admin user
            username: Username to get information about

        Returns:
            User information or error
        """
        # Check admin privileges
        if error := require_admin(authenticated_username, self.db_session):
            return error

        if not username:
            return [{"t": "error", "text": "Usage: hop3 admin:user:info <username>"}]

        # Find the user
        user = self.db_session.query(User).filter_by(username=username).first()
        if not user:
            return [{"t": "error", "text": f"User '{username}' not found"}]

        roles = ", ".join(role.name for role in user.roles) if user.roles else "None"

        return [
            {"t": "text", "text": "User Information"},
            {"t": "text", "text": "=" * 40},
            {"t": "text", "text": f"Username: {user.username}"},
            {"t": "text", "text": f"Email: {user.email}"},
            {"t": "text", "text": f"Active: {user.active}"},
            {"t": "text", "text": f"Admin: {user.is_admin}"},
            {"t": "text", "text": f"Roles: {roles}"},
            {"t": "text", "text": f"Login count: {user.login_count}"},
            {"t": "text", "text": f"Current login: {user.current_login_at or 'Never'}"},
            {"t": "text", "text": f"Last login: {user.last_login_at or 'Never'}"},
            {
                "t": "text",
                "text": f"Confirmed at: {user.confirmed_at or 'Not confirmed'}",
            },
            {"t": "text", "text": f"Created: {user.created_at}"},
            {"t": "text", "text": f"Updated: {user.updated_at}"},
        ]


@register
@dataclass(frozen=True)
class AdminUserGenerateTokenCmd(Command):
    """Generate a new API token for a user (bootstrap helper).

    Usage: hop3 admin:user:generate-token <username>

    This is useful for bootstrapping or when a user has lost their token.

    Examples:
        hop3 admin:user:generate-token john
    """

    db_session: Session
    name: ClassVar[str] = "admin:user:generate-token"
    # Needs authenticated username for permission checks
    pass_username: ClassVar[bool] = True

    def call(self, authenticated_username: str = "", username: str = "", *args):
        """Generate a new API token for a user.

        Args:
            authenticated_username: The authenticated admin user
            username: Username to generate token for

        Returns:
            Token or error
        """
        # Check admin privileges
        if error := require_admin(authenticated_username, self.db_session):
            return error

        if not username:
            return [
                {
                    "t": "error",
                    "text": "Usage: hop3 admin:user:generate-token <username>",
                }
            ]

        # Find the user
        user = self.db_session.query(User).filter_by(username=username).first()
        if not user:
            return [{"t": "error", "text": f"User '{username}' not found"}]

        if not user.active:
            return [
                {
                    "t": "error",
                    "text": f"User '{username}' is disabled. Enable the account first.",
                }
            ]

        # Generate token
        scopes = ["authenticated"]
        if user.is_admin:
            scopes.append("admin")

        token = create_token(username, scopes=scopes)

        return [
            {"t": "text", "text": f"API token generated for user: {username}"},
            {"t": "text", "text": ""},
            {"t": "text", "text": "Token:"},
            {"t": "text", "text": token},
            {"t": "text", "text": ""},
            {"t": "text", "text": "The user should save this to their config file:"},
            {"t": "text", "text": f'api_token = "{token}"'},
        ]
