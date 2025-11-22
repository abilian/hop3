# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL plugin for Hop3."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hop3.core.hooks import hookimpl

from . import cli
from .admin import PostgresAdmin
from .postgres import PostgresqlService

assert cli


class PostgresqlPlugin:
    """PostgreSQL service plugin for Hop3."""

    name = "postgresql"

    @hookimpl
    def get_service_strategies(self) -> list:
        """Return PostgreSQL service strategy."""
        return [PostgresqlService]


class PostgresPluginProvider(Provider):
    """DI provider for PostgreSQL services.

    Provides PostgresAdmin for centralized PostgreSQL configuration
    and connection management.

    Configuration is read from environment variables with POSTGRES_ prefix.
    """

    scope = Scope.APP

    @provide
    def get_postgres_admin(self) -> PostgresAdmin:
        """Provide PostgreSQL admin service.

        Returns:
            PostgresAdmin instance configured from POSTGRES_* environment variables
        """
        return PostgresAdmin.from_config()


@hookimpl
def get_di_providers() -> list:
    """Register PostgreSQL DI providers.

    This hook is called by the DI container during initialization
    to collect providers from all plugins.

    Returns:
        List containing PostgresPluginProvider instance
    """
    return [PostgresPluginProvider()]


# Auto-register plugin instance when module is imported
plugin = PostgresqlPlugin()
