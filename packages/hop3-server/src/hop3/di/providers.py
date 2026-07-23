# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[typing-only-third-party-import, typing-only-standard-library-import]

"""Dishka providers for Hop3 services."""

from __future__ import annotations

from collections.abc import Iterator

from dishka import Provider, Scope, provide
from sqlalchemy.orm import Session

from hop3.config import HopConfig
from hop3.core.backup import BackupManager
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
    EnvVarRepository,
    RevokedTokenRepository,
    RoleRepository,
    UserRepository,
)
from hop3.orm.session import get_session_factory
from hop3.platform.certificates import CertificatesManager


class ConfigProvider(Provider):
    """Provides configuration to the application."""

    scope = Scope.APP

    @provide
    def get_config(self) -> HopConfig:
        """
        Get or create the singleton config instance.

        Returns:
            HopConfig: The application configuration
        """
        return HopConfig.get_instance()


class DatabaseProvider(Provider):
    """
    Provides database sessions for REQUEST scope.

    Each request/operation gets a fresh database session that is automatically
    closed when the request context exits.
    """

    scope = Scope.REQUEST

    @provide
    def get_session(self, config: HopConfig) -> Iterator[Session]:
        """
        Provide database session for REQUEST scope.

        This uses a context manager pattern to ensure the session is properly
        closed after use, even if an exception occurs.

        Dependencies:
            config: Application configuration (for database URI)

        Yields:
            SQLAlchemy Session instance

        Note:
            The session is automatically committed on successful completion
            and rolled back on exceptions.
        """
        session_factory = get_session_factory()
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class HopCoreProvider(Provider):
    """Provides Hop3 core services."""

    scope = Scope.APP

    # CertificatesManager is stateless, so APP scope is appropriate
    # It will be created once and reused throughout the application lifetime
    certificates_manager = provide(CertificatesManager)

    @provide(scope=Scope.REQUEST)
    def get_backup_manager(
        self,
        backup_repo: BackupRepository,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
    ) -> BackupManager:
        """
        Provide BackupManager instance.

        BackupManager requires repositories, so it uses REQUEST scope
        to get fresh repository instances for each request/operation.

        Dependencies:
            backup_repo: Repository for backup operations
            app_repo: Repository for app operations
            addon_credential_repo: Repository for addon credential operations

        Returns:
            BackupManager instance configured with the repositories
        """
        return BackupManager(
            backup_repo=backup_repo,
            app_repo=app_repo,
            addon_credential_repo=addon_credential_repo,
        )


class RepositoryProvider(Provider):
    """
    Provides repository instances for REQUEST scope.

    Each repository wraps database operations for a specific model type,
    providing a cleaner API than raw SQLAlchemy queries.
    """

    scope = Scope.REQUEST

    @provide
    def user_repo(self, db_session: Session) -> UserRepository:
        """Provide UserRepository instance."""
        return UserRepository(session=db_session)

    @provide
    def role_repo(self, db_session: Session) -> RoleRepository:
        """Provide RoleRepository instance."""
        return RoleRepository(session=db_session)

    @provide
    def app_repo(self, db_session: Session) -> AppRepository:
        """Provide AppRepository instance."""
        return AppRepository(session=db_session)

    @provide
    def addon_credential_repo(self, db_session: Session) -> AddonCredentialRepository:
        """Provide AddonCredentialRepository instance."""
        return AddonCredentialRepository(session=db_session)

    @provide
    def backup_repo(self, db_session: Session) -> BackupRepository:
        """Provide BackupRepository instance."""
        return BackupRepository(session=db_session)

    @provide
    def env_var_repo(self, db_session: Session) -> EnvVarRepository:
        """Provide EnvVarRepository instance."""
        return EnvVarRepository(session=db_session)

    @provide
    def revoked_token_repo(self, db_session: Session) -> RevokedTokenRepository:
        """Provide RevokedTokenRepository instance."""
        return RevokedTokenRepository(session=db_session)


# Future providers to add:
# - GitServiceProvider (for git operations)
# etc.
