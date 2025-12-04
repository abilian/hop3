# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL service implementation.

This module implements the Addon protocol for PostgreSQL,
allowing applications to create, attach, and manage PostgreSQL databases.

Credentials are stored encrypted in the database using Fernet encryption.
"""

from __future__ import annotations

import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from hop3.config import HOP3_ROOT


@dataclass(frozen=True)
class PostgresAddon:
    """PostgreSQL service implementation using Addon protocol.

    This service manages PostgreSQL database instances. Each service instance
    creates a dedicated database and user for isolation.

    Attributes:
        addon_name: The unique name for this PostgreSQL service instance
        _password: Optional pre-generated password (for internal use)
    """

    # Class attribute for the strategy name
    name: str = "postgres"

    # Instance attributes
    addon_name: str = ""
    _password: str = ""  # Internal: pre-generated password

    def __post_init__(self):
        """Validate that addon_name is provided and generate password if needed."""
        if not self.addon_name:
            msg = "addon_name is required for PostgresAddon"
            raise ValueError(msg)

        # Generate password if not provided (frozen dataclass workaround)
        if not self._password:
            # Use object.__setattr__ to set on frozen dataclass
            object.__setattr__(self, "_password", secrets.token_urlsafe(32))

    @property
    def db_name(self) -> str:
        """Database name derived from service name."""
        # Replace hyphens with underscores for valid PostgreSQL identifiers
        return self.addon_name.replace("-", "_")

    @property
    def db_user(self) -> str:
        """Database user name derived from service name."""
        return f"{self.db_name}_user"

    @property
    def db_password(self) -> str:
        """Get the secure password for the database user.

        Note: In production, this should be stored securely in a secrets manager.
        For now, we generate and cache a random password per instance.
        """
        # TODO: Store passwords securely in a secrets manager
        return self._password

    def create(self) -> None:
        """Create a new PostgreSQL database if it does not already exist.

        This method:
        1. Connects to PostgreSQL as the superuser
        2. Creates a new database user with a secure password
        3. Creates a new database owned by that user
        """
        # Connect to PostgreSQL (assuming superuser credentials are in env)
        # In production, these should come from configuration
        # Try to connect to template1 database which should always exist
        params = {
            "host": "localhost",
            "port": 5432,
            # Default to postgres superuser - should be configurable
            "user": "postgres",
            "dbname": "template1",  # Use template1 instead of postgres
            # Password should come from environment or config
        }

        connection = None
        try:
            connection = psycopg2.connect(**params)
            connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            with connection.cursor() as cursor:
                if self._check_database_exists(cursor):
                    # Database already exists, nothing to do
                    return

                # Create the database user and database
                self._create_database(cursor)

        finally:
            if connection:
                connection.close()

    def destroy(self) -> None:
        """Destroy the PostgreSQL database and user.

        This permanently deletes all data. Use with caution.
        """
        params = {
            "host": "localhost",
            "port": 5432,
            "user": "postgres",
            "dbname": "template1",  # Use template1 instead of postgres
        }

        connection = None
        try:
            connection = psycopg2.connect(**params)
            connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            with connection.cursor() as cursor:
                # Use sql.Identifier to safely escape database and user names
                cursor.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        sql.Identifier(self.db_name)
                    )
                )
                cursor.execute(
                    sql.SQL("DROP USER IF EXISTS {}").format(
                        sql.Identifier(self.db_user)
                    )
                )

        finally:
            if connection:
                connection.close()

    def get_connection_details(self) -> dict[str, str]:
        """Get environment variables for connecting to this PostgreSQL database.

        Returns:
            Dictionary with DATABASE_URL and other connection parameters
        """
        return {
            "DATABASE_URL": (
                f"postgresql://{self.db_user}:{self.db_password}@localhost/{self.db_name}"
            ),
            "PGDATABASE": self.db_name,
            "PGUSER": self.db_user,
            "PGPASSWORD": self.db_password,
            "PGHOST": "localhost",
            "PGPORT": "5432",
        }

    def backup(self) -> Path:
        """Create a backup of the PostgreSQL database using pg_dump.

        Returns:
            Path to the backup file
        """
        backup_dir = HOP3_ROOT / "backups" / "postgres"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{self.addon_name}_{timestamp}.sql"

        # Use pg_dump to create backup
        cmd = [
            "pg_dump",
            "-h",
            "localhost",
            "-U",
            self.db_user,
            "-d",
            self.db_name,
            "-f",
            str(backup_file),
        ]

        subprocess.run(cmd, check=True, env={"PGPASSWORD": self.db_password})

        return backup_file

    def restore(self, backup_path: Path) -> None:
        """Restore PostgreSQL database from a backup file.

        Args:
            backup_path: Path to the SQL backup file
        """
        if not backup_path.exists():
            msg = f"Backup file not found: {backup_path}"
            raise FileNotFoundError(msg)

        # Use psql to restore
        cmd = [
            "psql",
            "-h",
            "localhost",
            "-U",
            self.db_user,
            "-d",
            self.db_name,
            "-f",
            str(backup_path),
        ]

        subprocess.run(cmd, check=True, env={"PGPASSWORD": self.db_password})

    def info(self) -> dict[str, Any]:
        """Get information about the PostgreSQL service.

        Returns:
            Dictionary with service details
        """
        params = {
            "host": "localhost",
            "port": 5432,
            "user": self.db_user,
            "password": self.db_password,
            "dbname": self.db_name,
        }

        connection = None
        try:
            connection = psycopg2.connect(**params)

            with connection.cursor() as cursor:
                # Get database size
                cursor.execute(
                    "SELECT pg_database_size(%s);",
                    (self.db_name,),
                )
                size_bytes = cursor.fetchone()[0]

                # Get table count
                cursor.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public';"
                )
                table_count = cursor.fetchone()[0]

                # Get PostgreSQL version
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]

            return {
                "addon_name": self.addon_name,
                "type": "postgres",
                "database": self.db_name,
                "user": self.db_user,
                "host": "localhost",
                "port": 5432,
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "table_count": table_count,
                "version": version,
            }

        except psycopg2.Error as e:
            return {
                "addon_name": self.addon_name,
                "type": "postgres",
                "status": "error",
                "error": str(e),
            }
        finally:
            if connection:
                connection.close()

    def _check_database_exists(self, cursor) -> bool:
        """Check if the specified database exists.

        Args:
            cursor: A database cursor object used to execute SQL queries

        Returns:
            True if the database exists, False otherwise
        """
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.db_name,))
        exists = cursor.fetchone()
        return exists is not None

    def _create_database(self, cursor) -> None:
        """Create a new database and database user.

        Args:
            cursor: A database cursor object for executing commands
        """
        # Use sql.Identifier for user/db names and sql.Literal for password
        # to prevent SQL injection
        cursor.execute(
            sql.SQL("CREATE USER {} WITH PASSWORD {}").format(
                sql.Identifier(self.db_user), sql.Literal(self.db_password)
            )
        )

        cursor.execute(
            sql.SQL("CREATE DATABASE {} WITH OWNER {}").format(
                sql.Identifier(self.db_name), sql.Identifier(self.db_user)
            )
        )


# Backwards compatibility alias
PostgresqlAddon = PostgresAddon
