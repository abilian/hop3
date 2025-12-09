# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""MySQL plugin for Hop3."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hop3.core.hooks import hookimpl

from . import cli
from .admin import MySQLAdmin
from .mysql import MySQLAddon

assert cli


class MySQLPlugin:
    """MySQL addon plugin for Hop3."""

    name = "mysql"

    @hookimpl
    def get_addons(self) -> list:
        """Return MySQL addon implementation."""
        return [MySQLAddon]


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
