# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL administration service for dependency injection.

This module provides a PostgresAdmin service that manages PostgreSQL
connection configuration and can be injected via Dishka DI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3.config import HopConfig


@dataclass(frozen=True)
class PostgresAdmin:
    """PostgreSQL administration service.

    This service provides centralized configuration for PostgreSQL
    connections and operations. It's designed to be injected via
    Dishka DI for easier testing and configuration management.

    This is a lightweight service that provides connection parameters.
    The actual PostgreSQL operations are handled by PostgresService
    instances, which can use this admin service for connection details.

    Attributes:
        host: PostgreSQL server host
        port: PostgreSQL server port
        superuser: PostgreSQL superuser name
        superuser_password: PostgreSQL superuser password (optional)
    """

    host: str
    port: int
    superuser: str
    superuser_password: str | None = None

    @classmethod
    def from_config(cls, config: HopConfig) -> PostgresAdmin:
        """Create PostgresAdmin from application configuration.

        Args:
            config: Application configuration

        Returns:
            PostgresAdmin instance configured from HopConfig
        """
        return cls(
            host=config.postgres_host,
            port=config.postgres_port,
            superuser=config.postgres_superuser,
            superuser_password=getattr(config, "postgres_superuser_password", None),
        )

    def get_connection_params(self, dbname: str = "template1") -> dict[str, any]:
        """Get connection parameters for psycopg2.

        Args:
            dbname: Database name to connect to (defaults to template1)

        Returns:
            Dictionary with connection parameters for psycopg2.connect()
        """
        params = {
            "host": self.host,
            "port": self.port,
            "user": self.superuser,
            "dbname": dbname,
        }

        if self.superuser_password:
            params["password"] = self.superuser_password

        return params

    def get_dsn(self, dbname: str = "template1", include_password: bool = False) -> str:
        """Get Data Source Name (DSN) connection string.

        Args:
            dbname: Database name
            include_password: Whether to include password in DSN

        Returns:
            PostgreSQL DSN string
        """
        if include_password and self.superuser_password:
            return (
                f"postgresql://{self.superuser}:{self.superuser_password}"
                f"@{self.host}:{self.port}/{dbname}"
            )
        return f"postgresql://{self.superuser}@{self.host}:{self.port}/{dbname}"
