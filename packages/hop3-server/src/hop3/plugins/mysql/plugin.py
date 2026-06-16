# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""MySQL plugin for Hop3."""

from __future__ import annotations

import logging

from dishka import Provider, Scope, provide

from hop3.core.hooks import hookimpl
from hop3.core.protocols import HealthCheckResult

from . import cli
from .admin import MySQLAdmin
from .mysql import MySQLAddon

assert cli

logger = logging.getLogger(__name__)

# Check if mysql.connector is available
_MYSQL_AVAILABLE = False
try:
    import mysql.connector

    _MYSQL_AVAILABLE = True
except ImportError:
    mysql = None  # type: ignore[assignment]


class MySQLHealthCheck:
    """Health check for MySQL connectivity."""

    name = "mysql"

    def is_configured(self) -> bool:
        """Check if MySQL is configured with admin credentials."""
        if not _MYSQL_AVAILABLE:
            return False
        try:
            admin = MySQLAdmin.from_config()
            return admin.superuser_password is not None
        except Exception:
            return False

    def check(self) -> HealthCheckResult:
        """Test MySQL connectivity."""
        if not _MYSQL_AVAILABLE:
            return HealthCheckResult(
                name="MySQL",
                passed=True,
                message="MySQL connector not installed (skipped)",
            )

        try:
            admin = MySQLAdmin.from_config()

            if not admin.superuser_password:
                return HealthCheckResult(
                    name="MySQL",
                    passed=True,
                    message="Not configured (no superuser password)",
                )

            # Try to connect
            assert mysql is not None  # checked by _MYSQL_AVAILABLE above
            connection = mysql.connector.connect(**admin.get_connection_params())
            cursor = connection.cursor()
            cursor.execute("SELECT VERSION()")
            row = cursor.fetchone()
            cursor.close()
            connection.close()

            # fetchone() returns a tuple for standard cursor
            version_str = str(row[0]) if row else "unknown"  # type: ignore[index]
            return HealthCheckResult(
                name="MySQL",
                passed=True,
                message="Connection successful",
                details={"version": version_str},
            )

        except Exception as e:
            # Catch all errors including mysql.connector.Error
            error_code = getattr(e, "errno", None)
            return HealthCheckResult(
                name="MySQL",
                passed=False,
                message=f"Connection failed: {e}",
                details={"error_code": error_code},
            )


class MySQLPlugin:
    """MySQL addon plugin for Hop3."""

    name = "mysql"

    @hookimpl
    def get_addons(self) -> list:
        """Return MySQL addon implementation."""
        return [MySQLAddon]

    @hookimpl
    def get_health_checks(self) -> list:
        """Return MySQL health check."""
        return [MySQLHealthCheck()]

    @hookimpl
    def cli_commands(self) -> list:
        """Contribute `addon mysql <verb>` commands to the CLI."""
        return cli.COMMANDS


class MySQLPluginProvider(Provider):
    """DI provider for MySQL addon infrastructure.

    Provides MySQLAdmin for centralized MySQL configuration
    and connection management.

    Configuration is read from environment variables with MYSQL_ prefix.
    """

    scope = Scope.APP

    @provide
    def get_mysql_admin(self) -> MySQLAdmin:
        """Provide MySQL administration interface.

        Returns:
            MySQLAdmin instance configured from MYSQL_* environment variables
        """
        return MySQLAdmin.from_config()


@hookimpl
def get_di_providers() -> list:
    """Register MySQL DI providers.

    This hook is called by the DI container during initialization
    to collect providers from all plugins.

    Returns:
        List containing MySQLPluginProvider instance
    """
    return [MySQLPluginProvider()]


# Auto-register plugin instance when module is imported
plugin = MySQLPlugin()
