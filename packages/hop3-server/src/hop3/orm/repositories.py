# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Repository classes for database access using Advanced Alchemy.

This module provides repository classes that encapsulate database queries,
following the repository pattern. Each repository provides methods for
common query operations on its model type.

Usage:
    from hop3.orm.repositories import UserRepository

    # In commands (injected via Dishka)
    @dataclass
    class MyCommand:
        user_repo: UserRepository

        def call(self):
            user = self.user_repo.get_by_username("admin")

    # Manual instantiation
    user_repo = UserRepository(session=db_session)
    user = user_repo.get_by_username("admin")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from advanced_alchemy.repository import ModelT, SQLAlchemySyncRepository
from sqlalchemy import select

from .addon_credential import AddonCredential
from .app import App, AppStateEnum
from .backup import Backup
from .env import EnvVar
from .port_claim import PortClaim
from .revoked_token import RevokedToken
from .security import Role, User

if TYPE_CHECKING:
    pass


class BaseRepository(SQLAlchemySyncRepository[ModelT]):
    """Base class for repositories."""


# =============================================================================
# User and Role Repositories
# =============================================================================


class UserRepository(BaseRepository[User]):
    """Repository for managing User entities."""

    model_type = User

    def get_by_username(self, username: str) -> User | None:
        """Get user by username.

        Args:
            username: The username to search for

        Returns:
            User if found, None otherwise
        """
        return self.get_one_or_none(username=username)

    def get_by_email(self, email: str) -> User | None:
        """Get user by email address.

        Args:
            email: The email to search for

        Returns:
            User if found, None otherwise
        """
        return self.get_one_or_none(email=email)

    def list_all_ordered(self) -> list[User]:
        """List all users ordered by username.

        Returns:
            List of all users sorted alphabetically by username
        """
        stmt = select(User).order_by(User.username)
        return list(self.session.scalars(stmt).all())

    def list_active(self) -> list[User]:
        """List all active users.

        Returns:
            List of users with active=True
        """
        return list(self.get_many(active=True))

    def username_exists(self, username: str) -> bool:
        """Check if a username already exists.

        Args:
            username: The username to check

        Returns:
            True if username exists, False otherwise
        """
        return self.exists(username=username)

    def email_exists(self, email: str) -> bool:
        """Check if an email already exists.

        Args:
            email: The email to check

        Returns:
            True if email exists, False otherwise
        """
        return self.exists(email=email)


class RoleRepository(BaseRepository[Role]):
    """Repository for managing Role entities."""

    model_type = Role

    def get_by_name(self, name: str) -> Role | None:
        """Get role by name.

        Args:
            name: The role name to search for

        Returns:
            Role if found, None otherwise
        """
        return self.get_one_or_none(name=name)

    def get_admin_role(self) -> Role | None:
        """Get the admin role.

        Returns:
            The admin Role if it exists, None otherwise
        """
        return self.get_one_or_none(name="admin")


# =============================================================================
# App Repository
# =============================================================================


class AppRepository(BaseRepository[App]):
    """Repository for managing App entities."""

    model_type = App

    def get_by_name(self, name: str) -> App | None:
        """Get app by name.

        Args:
            name: The app name to search for

        Returns:
            App if found, None otherwise
        """
        return self.get_one_or_none(name=name)

    def list_all_ordered(self) -> list[App]:
        """List all apps ordered by name.

        Returns:
            List of all apps sorted alphabetically by name
        """
        stmt = select(App).order_by(App.name)
        return list(self.session.scalars(stmt).all())

    def list_by_run_states(self, states: list[AppStateEnum]) -> list[App]:
        """List apps in specified run states.

        Args:
            states: List of AppStateEnum values to filter by

        Returns:
            List of apps in any of the specified states
        """
        stmt = select(App).where(App.run_state.in_(states))
        return list(self.session.scalars(stmt).all())

    def list_transitional(self) -> list[App]:
        """List apps in transitional states (STARTING, STOPPING).

        Returns:
            List of apps that are currently starting or stopping
        """
        return self.list_by_run_states([AppStateEnum.STARTING, AppStateEnum.STOPPING])

    def app_exists(self, name: str) -> bool:
        """Check if an app with the given name exists.

        Args:
            name: The app name to check

        Returns:
            True if app exists, False otherwise
        """
        return self.exists(name=name)


# =============================================================================
# AddonCredential Repository
# =============================================================================


class AddonCredentialRepository(BaseRepository[AddonCredential]):
    """Repository for managing AddonCredential entities."""

    model_type = AddonCredential

    def get_by_app_id(self, app_id: int) -> list[AddonCredential]:
        """Get all credentials for an app.

        Args:
            app_id: The app ID to search for

        Returns:
            List of addon credentials for the app
        """
        return list(self.get_many(app_id=app_id))

    def get_by_app_addon(
        self,
        app_id: int,
        addon_type: str,
        addon_name: str,
    ) -> AddonCredential | None:
        """Get credential for a specific app and addon combination.

        Args:
            app_id: The app ID
            addon_type: Type of addon (e.g., "postgresql", "redis")
            addon_name: Name of the addon instance

        Returns:
            AddonCredential if found, None otherwise
        """
        return self.get_one_or_none(
            app_id=app_id,
            addon_type=addon_type,
            addon_name=addon_name,
        )

    def list_by_addon(
        self,
        addon_type: str,
        addon_name: str,
    ) -> list[AddonCredential]:
        """List all credentials for a specific addon.

        Args:
            addon_type: Type of addon (e.g., "postgresql", "redis")
            addon_name: Name of the addon instance

        Returns:
            List of credentials attached to this addon
        """
        return list(self.get_many(addon_type=addon_type, addon_name=addon_name))

    def get_by_addon_name(self, addon_name: str) -> AddonCredential | None:
        """Get credential by addon name only.

        Args:
            addon_name: Name of the addon instance

        Returns:
            AddonCredential if found, None otherwise
        """
        return self.get_one_or_none(addon_name=addon_name)

    def list_by_app_and_type(
        self, app_id: int, addon_type: str
    ) -> list[AddonCredential]:
        """Same-type addon credentials attached to an app, oldest first (by id).

        Used to pick/demote the primary addon among same-type siblings.
        """
        stmt = (
            select(AddonCredential)
            .where(
                AddonCredential.app_id == app_id,
                AddonCredential.addon_type == addon_type,
            )
            .order_by(AddonCredential.id)
        )
        return list(self.session.scalars(stmt).all())

    def list_all_with_apps(self) -> list[AddonCredential]:
        """List all credentials with app information eager loaded.

        Returns:
            List of all addon credentials
        """
        stmt = select(AddonCredential).join(App)
        return list(self.session.scalars(stmt).all())


# =============================================================================
# Backup Repository
# =============================================================================


class BackupRepository(BaseRepository[Backup]):
    """Repository for managing Backup entities."""

    model_type = Backup

    def get_by_backup_id(self, backup_id: str) -> Backup | None:
        """Get backup by searching for backup_id in remote_path.

        The backup_id is typically a UUID that appears in the remote_path.

        Args:
            backup_id: The backup identifier to search for

        Returns:
            Backup if found, None otherwise
        """
        stmt = select(Backup).where(Backup.remote_path.contains(backup_id))
        return self.session.scalars(stmt).first()

    def get_by_backup_id_with_app(self, backup_id: str) -> Backup | None:
        """Get backup by backup_id with app relationship loaded.

        Args:
            backup_id: The backup identifier to search for

        Returns:
            Backup if found, None otherwise
        """
        stmt = select(Backup).join(App).where(Backup.remote_path.contains(backup_id))
        return self.session.scalars(stmt).first()

    def list_by_app_name(
        self,
        app_name: str | None = None,
        limit: int = 20,
    ) -> list[Backup]:
        """List backups, optionally filtered by app name.

        Args:
            app_name: Optional app name to filter by
            limit: Maximum number of backups to return

        Returns:
            List of backups, most recent first
        """
        stmt = select(Backup).join(App)
        if app_name:
            stmt = stmt.where(App.name == app_name)
        stmt = stmt.order_by(Backup.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def list_all_with_apps(self) -> list[Backup]:
        """List all backups with app information.

        Returns:
            List of all backups with app relationship loaded
        """
        stmt = select(Backup).join(App).order_by(Backup.created_at.desc())
        return list(self.session.scalars(stmt).all())


# =============================================================================
# EnvVar Repository
# =============================================================================


class EnvVarRepository(BaseRepository[EnvVar]):
    """Repository for managing EnvVar entities."""

    model_type = EnvVar

    def get_by_app_and_name(self, app_id: int, name: str) -> EnvVar | None:
        """Get environment variable by app ID and variable name.

        Args:
            app_id: The app ID
            name: The environment variable name

        Returns:
            EnvVar if found, None otherwise
        """
        return self.get_one_or_none(app_id=app_id, name=name)

    def list_by_app_id(self, app_id: int) -> list[EnvVar]:
        """List all environment variables for an app.

        Args:
            app_id: The app ID

        Returns:
            List of environment variables for the app
        """
        return list(self.get_many(app_id=app_id))


# =============================================================================
# RevokedToken Repository
# =============================================================================


class RevokedTokenRepository(BaseRepository[RevokedToken]):
    """Repository for managing RevokedToken entities."""

    model_type = RevokedToken

    def get_by_jti(self, jti: str) -> RevokedToken | None:
        """Get revoked token by JWT ID.

        Args:
            jti: The JWT ID (from the 'jti' claim)

        Returns:
            RevokedToken if found, None otherwise
        """
        return self.get_one_or_none(jti=jti)

    def is_revoked(self, jti: str) -> bool:
        """Check if a token is revoked.

        Args:
            jti: The JWT ID to check

        Returns:
            True if the token is revoked, False otherwise
        """
        return self.exists(jti=jti)


class PortClaimRepository(BaseRepository[PortClaim]):
    """Repository for the host-wide fixed-port claim registry."""

    model_type = PortClaim

    def find_active(self, number: int, protocol: str = "tcp") -> PortClaim | None:
        """Return the claim holding ``(number, protocol)``, or None if free."""
        return self.get_one_or_none(number=number, protocol=protocol)

    def get_by_app_id(self, app_id: int) -> list[PortClaim]:
        """Return all port claims held by an app."""
        return list(self.get_many(app_id=app_id))

    def find_by_addon(self, addon_type: str, addon_name: str) -> PortClaim | None:
        """Return the exposure claim for an addon instance, or None."""
        return self.get_one_or_none(addon_type=addon_type, addon_name=addon_name)
