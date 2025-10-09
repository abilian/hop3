# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL plugin for Hop3."""

from __future__ import annotations

from hop3.core.hooks import hookimpl

from . import cli
from .postgres import PostgresqlAddon

assert cli


class PostgresqlPlugin:
    """PostgreSQL service plugin for Hop3."""

    name = "postgresql"

    @hookimpl
    def get_service_strategies(self) -> list:
        """Return PostgreSQL service strategy."""
        return [PostgresqlAddon]


# Auto-register plugin instance when module is imported
plugin = PostgresqlPlugin()
