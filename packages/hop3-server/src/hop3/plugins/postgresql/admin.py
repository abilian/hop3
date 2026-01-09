# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL administration service for dependency injection.

This module provides a PostgresAdmin service that manages PostgreSQL
connection configuration and can be injected via Dishka DI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from hop3.lib.config import Config


def _get_hop3_config() -> Config:
    """Get the global hop3 configuration.

    Reads from HOP3_ROOT/hop3-server.toml if it exists,
    otherwise falls back to environment variables.
    """
    hop3_root = Path(os.environ.get("HOP3_ROOT", "/home/hop3"))
    config_file = hop3_root / "hop3-server.toml"
    if config_file.exists():
        return Config(file=config_file)
    return Config()


@dataclass(frozen=True)
class PostgresAdmin:
    """PostgreSQL administration service.

    This service provides centralized configuration for PostgreSQL
    connections and operations. It's designed to be injected via
    Dishka DI for easier testing and configuration management.

    This is a lightweight service that provides connection parameters.
    The actual PostgreSQL operations are handled by PostgresAddon
    instances, which can use this admin service for connection details.

    Configuration can be provided in two ways:
    1. URI format (preferred for managed databases):
       - POSTGRES_ADMIN_URL=postgresql://user:password@host:port/dbname

    2. Individual settings (with POSTGRES_ prefix):
       - POSTGRES_HOST (default: localhost)
       - POSTGRES_PORT (default: 5432)
       - POSTGRES_SUPERUSER (default: postgres)
       - POSTGRES_SUPERUSER_PASSWORD (optional)

    Configuration is read from:
    - HOP3_ROOT/hop3-server.toml (if exists)
    - Environment variables (fallback)

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

        Supports two configuration styles:
        1. URI format: POSTGRES_ADMIN_URL=postgresql://user:pass@host:port/db
        2. Individual settings: POSTGRES_HOST, POSTGRES_PORT, etc.

        Args:
            config: Optional Config instance. If not provided, reads from
                   hop3-server.toml or environment variables.

        Returns:
            PostgresAdmin instance configured from config file or environment
        """
        if config is None:
            config = _get_hop3_config()

        # First, check for URI-style configuration
        # Try POSTGRES_ADMIN_URL first, then POSTGRES_URL
        admin_url = config.get_str("POSTGRES_ADMIN_URL", None)
        if not admin_url:
            admin_url = config.get_str("POSTGRES_URL", None)

        if admin_url:
            return cls.from_url(admin_url)

        # Fall back to individual settings with POSTGRES_ prefix
        prefix_config = Config(env_prefix="POSTGRES_")

        # Also check the main config file for POSTGRES_* keys
        host = prefix_config.get_str("HOST", None) or config.get_str(
            "POSTGRES_HOST", "localhost"
        )
        port_str = prefix_config.get_str("PORT", None) or config.get_str(
            "POSTGRES_PORT", "5432"
        )
        superuser = prefix_config.get_str("SUPERUSER", None) or config.get_str(
            "POSTGRES_SUPERUSER", "postgres"
        )
        password = prefix_config.get_str("SUPERUSER_PASSWORD", None) or config.get_str(
            "POSTGRES_SUPERUSER_PASSWORD", None
        )

        return cls(
            host=host,
            port=int(port_str),
            superuser=superuser,
            superuser_password=password,
        )

    @classmethod
    def from_url(cls, url: str) -> PostgresAdmin:
        """Create PostgresAdmin from a PostgreSQL URL.

        Args:
            url: PostgreSQL connection URL (postgresql://user:pass@host:port/db)

        Returns:
            PostgresAdmin instance

        Raises:
            ValueError: If URL is invalid or missing required components
        """
        parsed = urlparse(url)

        if parsed.scheme not in {"postgresql", "postgres"}:
            msg = f"Invalid PostgreSQL URL scheme: {parsed.scheme}"
            raise ValueError(msg)

        if not parsed.hostname:
            msg = "PostgreSQL URL must include a hostname"
            raise ValueError(msg)

        if not parsed.username:
            msg = "PostgreSQL URL must include a username"
            raise ValueError(msg)

        return cls(
            host=parsed.hostname,
            port=parsed.port or 5432,
            superuser=parsed.username,
            superuser_password=parsed.password,
        )

    def get_connection_params(self, dbname: str = "template1") -> dict[str, Any]:
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

    def get_dsn(
        self, dbname: str = "template1", *, include_password: bool = False
    ) -> str:
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
