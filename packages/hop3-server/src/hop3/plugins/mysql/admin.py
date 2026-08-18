# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
MySQL administration service for dependency injection.

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


def _find_mysql_socket() -> str | None:
    """
    Auto-detect MySQL/MariaDB unix socket path.

    Checks common socket locations across macOS and Linux.
    Returns the first existing socket path, or None.
    """
    common_paths = [
        "/tmp/mysql.sock",  # macOS (Homebrew MariaDB/MySQL)
        "/var/run/mysqld/mysqld.sock",  # Debian/Ubuntu
        "/var/lib/mysql/mysql.sock",  # RHEL/CentOS
        "/run/mysqld/mysqld.sock",  # Newer systemd-based distros
    ]
    for path in common_paths:
        if Path(path).exists():
            return path
    return None


def _get_hop3_config() -> Config:
    """
    Get the global hop3 configuration.

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
    """
    MySQL administration service.

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
       - MYSQL_HOST (default: 127.0.0.1)
       - MYSQL_PORT (default: 3306)
       - MYSQL_SUPERUSER (default: root)
       - MYSQL_SUPERUSER_PASSWORD (optional)
       - MYSQL_UNIX_SOCKET (optional, for local socket connections)

    Configuration is read from:
    - HOP3_ROOT/hop3-server.toml (if exists)
    - Environment variables (fallback)

    Attributes:
        host: MySQL server host
        port: MySQL server port
        superuser: MySQL superuser name
        superuser_password: MySQL superuser password (optional)
        unix_socket: Path to unix socket (optional, for local connections)
    """

    host: str
    port: int
    superuser: str
    superuser_password: str | None = None
    unix_socket: str | None = None

    @classmethod
    def from_config(cls, config: Config | None = None) -> MySQLAdmin:
        """
        Create MySQLAdmin from configuration.

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
            "MYSQL_HOST", "127.0.0.1"
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
        unix_socket: str | None = (
            prefix_config.get_str("UNIX_SOCKET", None)
            or config.get_str("MYSQL_UNIX_SOCKET", None)
            or None
        )

        # Auto-detect a unix socket ONLY when there is no password to connect
        # with. The socket is the Homebrew/MariaDB laptop pattern, where auth is
        # by peer credential and no password exists; a configured password means
        # someone provisioned a TCP account and that is what to use.
        #
        # Preferring the socket whenever one merely EXISTS overrode both the
        # configured MYSQL_HOST (127.0.0.1 by default) and the account the
        # installer creates — it makes 'hop3'@'127.0.0.1' with a password, and
        # says so when it fails: "MySQL must be running and accept a TCP
        # connection as 'hop3' on 127.0.0.1:3306". On a server hop3-server runs
        # as the `hop3` user, which cannot connect to mysqld's socket, so every
        # app declaring a mysql addon died on
        # "[Errno 13] Permission denied: '/var/run/mysqld/mysqld.sock'" —
        # seven of twenty golden apps, on a box where MySQL was running fine and
        # the installer had verified its own TCP connection.
        if not unix_socket and not password:
            unix_socket = _find_mysql_socket()

        # When using unix socket auth and no explicit superuser was configured,
        # default to the current OS user ONLY on macOS (Homebrew MariaDB pattern).
        # On Linux servers, MySQL root typically has socket peer auth, so keep "root".
        if unix_socket and superuser == "root" and not password:
            import sys  # ruff:ignore[import-outside-top-level]

            if sys.platform == "darwin":
                env_user = prefix_config.get_str("SUPERUSER", None) or config.get_str(
                    "MYSQL_SUPERUSER", None
                )
                if not env_user:
                    superuser = os.getenv("USER", "root")

        return cls(
            host=host,
            port=int(port_str),
            superuser=superuser,
            superuser_password=password,
            unix_socket=unix_socket,
        )

    @classmethod
    def from_url(cls, url: str) -> MySQLAdmin:
        """
        Create MySQLAdmin from a MySQL URL.

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
        """
        Get connection parameters for mysql-connector-python.

        If a unix_socket is configured, uses socket connection instead of TCP.
        This is needed for macOS/Linux where MariaDB uses unix_socket auth.

        Args:
            database: Database name to connect to (defaults to empty for admin)

        Returns:
            Dictionary with connection parameters for mysql.connector.connect()
        """
        params: dict[str, Any] = {
            "user": self.superuser,
        }

        if self.unix_socket:
            params["unix_socket"] = self.unix_socket
        else:
            params["host"] = self.host
            params["port"] = self.port

        if database:
            params["database"] = database

        if self.superuser_password:
            params["password"] = self.superuser_password

        return params

    def get_dsn(self, database: str = "", *, include_password: bool = False) -> str:
        """
        Get Data Source Name (DSN) connection string.

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
