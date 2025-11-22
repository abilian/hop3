# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dishka providers for Hop3 services."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hop3.config import HopConfig
from hop3.services.certificates import CertificatesManager


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


class HopServicesProvider(Provider):
    """Provides Hop3 core services."""

    scope = Scope.APP

    # CertificatesManager is stateless, so APP scope is appropriate
    # It will be created once and reused throughout the application lifetime
    certificates_manager = provide(CertificatesManager)

    # NOTE: BackupManager provider is commented out until we have DatabaseProvider
    # providing Session in REQUEST scope. BackupManager can still be created
    # manually with BackupManager(db_session) where needed.
    #
    # @provide(scope=Scope.REQUEST)
    # def get_backup_manager(self, db_session: Session) -> BackupManager:
    #     """Provide BackupManager instance.
    #
    #     BackupManager requires a database session, so it uses REQUEST scope
    #     to get a fresh session for each request/operation.
    #
    #     Dependencies:
    #         db_session: SQLAlchemy database session (from DatabaseProvider)
    #
    #     Returns:
    #         BackupManager instance configured with the current session
    #     """
    #     return BackupManager(db_session)


# Future providers to add:
# - DatabaseProvider (for ORM session management with REQUEST scope) - REQUIRED for BackupManager
# - GitServiceProvider (for git operations)
# etc.
