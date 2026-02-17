# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL plugin for Hop3."""

from __future__ import annotations

import logging

from dishka import Provider, Scope, provide

from hop3.core.hooks import hookimpl
from hop3.core.protocols import HealthCheckResult

from . import cli
from .admin import PostgresAdmin
from .postgres import PostgresqlAddon

assert cli

logger = logging.getLogger(__name__)

# Check if psycopg2 is available
_PSYCOPG2_AVAILABLE = False
try:
    import psycopg2

    _PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None  # type: ignore[assignment]


class PostgresHealthCheck:
    """Health check for PostgreSQL connectivity."""

    name = "postgresql"

    def is_configured(self) -> bool:
        """Check if PostgreSQL is configured with admin credentials."""
        if not _PSYCOPG2_AVAILABLE:
            return False
        try:
            admin = PostgresAdmin.from_config()
            return admin.superuser_password is not None
        except Exception:
            return False

    def check(self) -> HealthCheckResult:
        """Test PostgreSQL connectivity."""
        if not _PSYCOPG2_AVAILABLE:
            return HealthCheckResult(
                name="PostgreSQL",
                passed=True,
                message="psycopg2 not installed (skipped)",
            )

        try:
            admin = PostgresAdmin.from_config()

            if not admin.superuser_password:
                return HealthCheckResult(
                    name="PostgreSQL",
                    passed=True,
                    message="Not configured (no superuser password)",
                )

            # Try to connect
            connection = psycopg2.connect(**admin.get_connection_params())
            cursor = connection.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()
            cursor.close()
            connection.close()

            return HealthCheckResult(
                name="PostgreSQL",
                passed=True,
                message="Connection successful",
                details={"version": version[0] if version else "unknown"},
            )

        except psycopg2.Error as e:
            return HealthCheckResult(
                name="PostgreSQL",
                passed=False,
                message=f"Connection failed: {e}",
            )
        except Exception as e:
            return HealthCheckResult(
                name="PostgreSQL",
                passed=False,
                message=f"Health check error: {e}",
            )


class PostgresqlPlugin:
    """PostgreSQL addon plugin for Hop3."""

    name = "postgresql"

    @hookimpl
    def get_addons(self) -> list:
        """Return PostgreSQL addon implementation."""
        return [PostgresqlAddon]

    @hookimpl
    def get_health_checks(self) -> list:
        """Return PostgreSQL health check."""
        return [PostgresHealthCheck()]


class PostgresPluginProvider(Provider):
    """DI provider for PostgreSQL addon infrastructure.

    Provides PostgresAdmin for centralized PostgreSQL configuration
    and connection management.

    Configuration is read from environment variables with POSTGRES_ prefix.
    """

    scope = Scope.APP

    @provide
    def get_postgres_admin(self) -> PostgresAdmin:
        """Provide PostgreSQL administration interface.

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
