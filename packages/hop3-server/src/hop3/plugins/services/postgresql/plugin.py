# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL plugin for Hop3.

This plugin provides PostgreSQL database service capabilities to Hop3 applications.
"""

from __future__ import annotations

from hop3.core.hooks import hop3_hook_impl
from hop3.core.protocols import ServiceStrategy

from . import cli
from .postgres import PostgresService

assert cli


class PostgresqlPlugin:
    """PostgreSQL service plugin for Hop3.

    This plugin registers the PostgreSQL service strategy with the Hop3
    plugin system, allowing applications to create and attach PostgreSQL databases.
    """

    name = "postgresql"

    @hop3_hook_impl
    def get_service_strategies(self) -> list[type[ServiceStrategy]]:
        """Return PostgreSQL service strategy."""
        return [PostgresService]
