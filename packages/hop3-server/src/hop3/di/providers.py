# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dishka providers for Hop3 services."""

from __future__ import annotations

from collections.abc import Iterator

from dishka import Provider, Scope, provide
from sqlalchemy.orm import Session

from hop3.config import HopConfig
from hop3.core.backup import BackupManager
from hop3.orm.session import get_session_factory
from hop3.platform.certificates import CertificatesManager


class ConfigProvider(Provider):
    """Provides configuration to the application."""

    scope = Scope.APP

    @provide
    def get_config(self) -> HopConfig:
        """Get or create the singleton config instance.

        Returns:
            HopConfig: The application configuration
        """
        return HopConfig.get_instance()


class DatabaseProvider(Provider):
    """Provides database sessions for REQUEST scope.

    Each request/operation gets a fresh database session that is automatically
    closed when the request context exits.
    """

    scope = Scope.REQUEST

    @provide
    def get_session(self, config: HopConfig) -> Iterator[Session]:
        """Provide database session for REQUEST scope.

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
    def get_backup_manager(self, db_session: Session) -> BackupManager:
        """Provide BackupManager instance.

        BackupManager requires a database session, so it uses REQUEST scope
        to get a fresh session for each request/operation.

        Dependencies:
            db_session: SQLAlchemy database session (from DatabaseProvider)

        Returns:
            BackupManager instance configured with the current session
        """
        return BackupManager(db_session)


# Future providers to add:
# - GitServiceProvider (for git operations)
# etc.
