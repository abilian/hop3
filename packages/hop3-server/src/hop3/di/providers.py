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


# Future providers can be added here:
# - DatabaseProvider (for ORM session management with REQUEST scope)
# - BackupServiceProvider (for backup operations)
# - GitServiceProvider (for git operations)
# etc.
