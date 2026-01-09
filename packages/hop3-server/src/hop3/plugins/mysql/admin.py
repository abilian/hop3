# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""MySQL administration service for dependency injection.

This module provides a MySQLAdmin service that manages MySQL
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
class MySQLAdmin:
    """MySQL administration service.

    This service provides centralized configuration for MySQL
    connections and operations. It's designed to be injected via
    Dishka DI for easier testing and configuration management.

    This is a lightweight service that provides connection parameters.
    The actual MySQL operations are handled by MySQLAddon
    instances, which can use this admin service for connection details.

    Configuration can be provided in two ways:
    1. URI format (preferred for managed databases):
       - MYSQL_ADMIN_URL=mysql://user:password@host:port/dbname

    2. Individual settings (with MYSQL_ prefix):
       - MYSQL_HOST (default: localhost)
       - MYSQL_PORT (default: 3306)
       - MYSQL_SUPERUSER (default: root)
       - MYSQL_SUPERUSER_PASSWORD (optional)

    Configuration is read from:
    - HOP3_ROOT/hop3-server.toml (if exists)
    - Environment variables (fallback)

    Attributes:
        host: MySQL server host
        port: MySQL server port
        superuser: MySQL superuser name
        superuser_password: MySQL superuser password (optional)
    """

    host: str
    port: int
    superuser: str
    superuser_password: str | None = None

    @classmethod
    def from_config(cls, config: Config | None = None) -> MySQLAdmin:
        """Create MySQLAdmin from configuration.

        Supports two configuration styles:
        1. URI format: MYSQL_ADMIN_URL=mysql://user:pass@host:port/db
        2. Individual settings: MYSQL_HOST, MYSQL_PORT, etc.

        Args:
            config: Optional Config instance. If not provided, reads from
                   hop3-server.toml or environment variables.

        Returns:
            MySQLAdmin instance configured from config file or environment
        """
        if config is None:
            config = _get_hop3_config()

        # First, check for URI-style configuration
        # Try MYSQL_ADMIN_URL first, then MYSQL_URL
        admin_url = config.get_str("MYSQL_ADMIN_URL", None)
        if not admin_url:
            admin_url = config.get_str("MYSQL_URL", None)

        if admin_url:
            return cls.from_url(admin_url)

        # Fall back to individual settings with MYSQL_ prefix
        prefix_config = Config(env_prefix="MYSQL_")

        # Also check the main config file for MYSQL_* keys
        host = prefix_config.get_str("HOST", None) or config.get_str(
            "MYSQL_HOST", "localhost"
        )
        port_str = prefix_config.get_str("PORT", None) or config.get_str(
            "MYSQL_PORT", "3306"
        )
        superuser = prefix_config.get_str("SUPERUSER", None) or config.get_str(
            "MYSQL_SUPERUSER", "root"
        )
        password = prefix_config.get_str("SUPERUSER_PASSWORD", None) or config.get_str(
            "MYSQL_SUPERUSER_PASSWORD", None
        )

        return cls(
            host=host,
            port=int(port_str),
            superuser=superuser,
            superuser_password=password,
        )

    @classmethod
    def from_url(cls, url: str) -> MySQLAdmin:
        """Create MySQLAdmin from a MySQL URL.

        Args:
            url: MySQL connection URL (mysql://user:pass@host:port/db)

        Returns:
            MySQLAdmin instance

        Raises:
            ValueError: If URL is invalid or missing required components
        """
        parsed = urlparse(url)

        if parsed.scheme not in {"mysql", "mysql+pymysql", "mysql+mysqlconnector"}:
            msg = f"Invalid MySQL URL scheme: {parsed.scheme}"
            raise ValueError(msg)

        if not parsed.hostname:
            msg = "MySQL URL must include a hostname"
            raise ValueError(msg)

        if not parsed.username:
            msg = "MySQL URL must include a username"
            raise ValueError(msg)

        return cls(
            host=parsed.hostname,
            port=parsed.port or 3306,
            superuser=parsed.username,
            superuser_password=parsed.password,
        )

    def get_connection_params(self, database: str = "") -> dict[str, Any]:
        """Get connection parameters for mysql-connector-python.

        Args:
            database: Database name to connect to (defaults to empty for admin)

        Returns:
            Dictionary with connection parameters for mysql.connector.connect()
        """
        params: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "user": self.superuser,
        }

        if database:
            params["database"] = database

        if self.superuser_password:
            params["password"] = self.superuser_password

        return params

    def get_dsn(self, database: str = "", *, include_password: bool = False) -> str:
        """Get Data Source Name (DSN) connection string.

        Args:
            database: Database name
            include_password: Whether to include password in DSN

        Returns:
            MySQL DSN string
        """
        db_part = f"/{database}" if database else ""
        if include_password and self.superuser_password:
            return (
                f"mysql://{self.superuser}:{self.superuser_password}"
                f"@{self.host}:{self.port}{db_part}"
            )
        return f"mysql://{self.superuser}@{self.host}:{self.port}{db_part}"
