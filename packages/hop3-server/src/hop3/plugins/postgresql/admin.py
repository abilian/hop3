# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL administration service for dependency injection.

This module provides a PostgresAdmin service that manages PostgreSQL
connection configuration and can be injected via Dishka DI.
"""

from __future__ import annotations

from dataclasses import dataclass

from hop3.lib.config import Config


@dataclass(frozen=True)
class PostgresAdmin:
    """PostgreSQL administration service.

    This service provides centralized configuration for PostgreSQL
    connections and operations. It's designed to be injected via
    Dishka DI for easier testing and configuration management.

    This is a lightweight service that provides connection parameters.
    The actual PostgreSQL operations are handled by PostgresService
    instances, which can use this admin service for connection details.

    Configuration is read from environment variables with POSTGRES_ prefix:
    - POSTGRES_HOST (default: localhost)
    - POSTGRES_PORT (default: 5432)
    - POSTGRES_SUPERUSER (default: postgres)
    - POSTGRES_SUPERUSER_PASSWORD (optional)

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
    def from_config(cls, config: Config | None = None) -> PostgresAdmin:
        """Create PostgresAdmin from configuration.

        Args:
            config: Optional Config instance. If not provided, creates one with POSTGRES_ prefix.

        Returns:
            PostgresAdmin instance configured from environment/config file
        """
        if config is None:
            config = Config(env_prefix="POSTGRES_")

        return cls(
            host=config.get_str("HOST", "localhost"),
            port=config.get_int("PORT", 5432),
            superuser=config.get_str("SUPERUSER", "postgres"),
            superuser_password=config.get_str("SUPERUSER_PASSWORD", None),
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
