# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL service implementation.

This module implements the Addon protocol for PostgreSQL,
allowing applications to create, attach, and manage PostgreSQL databases.

Admin credentials are configured via environment variables:
- POSTGRES_HOST (default: localhost)
- POSTGRES_PORT (default: 5432)
- POSTGRES_SUPERUSER (default: postgres)
- POSTGRES_SUPERUSER_PASSWORD (required for most setups)

Addon passwords are stored persistently in HOP3_ROOT/addons/postgres/
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.errors import DuplicateObject
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from hop3.config import HOP3_ROOT

from .admin import PostgresAdmin


def _get_addon_secrets_dir() -> Path:
    """Get the directory for storing addon secrets."""
    secrets_dir = HOP3_ROOT / "addons" / "postgres"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    return secrets_dir


def _get_addon_secrets_file(addon_name: str) -> Path:
    """Get the secrets file path for an addon."""
    return _get_addon_secrets_dir() / f"{addon_name}.json"


def _load_addon_secrets(addon_name: str) -> dict[str, Any] | None:
    """Load stored secrets for an addon."""
    secrets_file = _get_addon_secrets_file(addon_name)
    if secrets_file.exists():
        with Path(secrets_file).open() as f:
            return json.load(f)
    return None


def _save_addon_secrets(addon_name: str, secrets_data: dict[str, Any]) -> None:
    """Save secrets for an addon."""
    secrets_file = _get_addon_secrets_file(addon_name)
    with Path(secrets_file).open("w") as f:
        json.dump(secrets_data, f, indent=2)
    # Secure the file
    secrets_file.chmod(0o600)


def _delete_addon_secrets(addon_name: str) -> None:
    """Delete stored secrets for an addon."""
    secrets_file = _get_addon_secrets_file(addon_name)
    if secrets_file.exists():
        secrets_file.unlink()


@dataclass(frozen=True)
class PostgresAddon:
    """PostgreSQL service implementation using Addon protocol.

    This service manages PostgreSQL database instances. Each service instance
    creates a dedicated database and user for isolation.

    Attributes:
        addon_name: The unique name for this PostgreSQL service instance
    """

    # Class attribute for the strategy name
    name: str = "postgres"

    # Instance attributes
    addon_name: str = ""

    def __post_init__(self):
        """Validate that addon_name is provided."""
        if not self.addon_name:
            msg = "addon_name is required for PostgresAddon"
            raise ValueError(msg)

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
        """Get the password for the database user.

        Returns the stored password if available, or generates a new one.
        """
        stored_secrets = _load_addon_secrets(self.addon_name)
        if stored_secrets and "password" in stored_secrets:
            return stored_secrets["password"]
        # Generate new password (will be stored during create())
        return secrets.token_urlsafe(32)

    def _get_admin(self) -> PostgresAdmin:
        """Get PostgreSQL admin connection configuration."""
        return PostgresAdmin.from_config()

    def _get_stored_password(self) -> str | None:
        """Get the stored password for this addon, if any."""
        secrets = _load_addon_secrets(self.addon_name)
        if secrets:
            return secrets.get("password")
        return None

    def create(self) -> None:
        """Create a new PostgreSQL database if it does not already exist.

        This method:
        1. Connects to PostgreSQL as admin user
        2. Creates a new database user with a secure password
        3. Creates a new database owned by that user
        4. Stores the password for future use

        If the database already exists but secrets are missing (e.g., after
        server reinstall), the password is regenerated and saved.
        """
        admin = self._get_admin()

        # Generate new password
        password = secrets.token_urlsafe(32)

        connection = None
        try:
            connection = psycopg2.connect(**admin.get_connection_params())
            connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            with connection.cursor() as cursor:
                # Check if database already exists
                cursor.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (self.db_name,),
                )
                db_exists = cursor.fetchone() is not None

                # Check if we have stored secrets
                existing_secrets = _load_addon_secrets(self.addon_name)

                if db_exists and existing_secrets:
                    # Database and secrets both exist - nothing to do
                    return

                if db_exists:
                    # Database exists but secrets are missing - regenerate password
                    # This can happen after server reinstall or secrets cleanup
                    # User may or may not exist, so try CREATE first, fall back to ALTER
                    try:
                        cursor.execute(
                            sql.SQL("CREATE USER {} WITH PASSWORD {}").format(
                                sql.Identifier(self.db_user),
                                sql.Literal(password),
                            )
                        )
                    except DuplicateObject:
                        # User exists, update password
                        cursor.execute(
                            sql.SQL("ALTER USER {} WITH PASSWORD {}").format(
                                sql.Identifier(self.db_user),
                                sql.Literal(password),
                            )
                        )
                else:
                    # Create user (ignore if already exists)
                    try:
                        cursor.execute(
                            sql.SQL("CREATE USER {} WITH PASSWORD {}").format(
                                sql.Identifier(self.db_user),
                                sql.Literal(password),
                            )
                        )
                    except DuplicateObject:
                        # User already exists, update password
                        cursor.execute(
                            sql.SQL("ALTER USER {} WITH PASSWORD {}").format(
                                sql.Identifier(self.db_user),
                                sql.Literal(password),
                            )
                        )

                    # Create database
                    cursor.execute(
                        sql.SQL("CREATE DATABASE {} WITH OWNER {}").format(
                            sql.Identifier(self.db_name),
                            sql.Identifier(self.db_user),
                        )
                    )

            # Store the password (always when we reach here)
            _save_addon_secrets(
                self.addon_name,
                {
                    "password": password,
                    "db_name": self.db_name,
                    "db_user": self.db_user,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        finally:
            if connection:
                connection.close()

    def destroy(self) -> None:
        """Destroy the PostgreSQL database and user.

        This permanently deletes all data. Use with caution.
        """
        admin = self._get_admin()

        connection = None
        try:
            connection = psycopg2.connect(**admin.get_connection_params())
            connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            with connection.cursor() as cursor:
                # Drop database
                cursor.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        sql.Identifier(self.db_name)
                    )
                )
                # Drop user
                cursor.execute(
                    sql.SQL("DROP USER IF EXISTS {}").format(
                        sql.Identifier(self.db_user)
                    )
                )

            # Delete stored secrets
            _delete_addon_secrets(self.addon_name)

        finally:
            if connection:
                connection.close()

    def get_connection_details(self) -> dict[str, str]:
        """Get environment variables for connecting to this PostgreSQL database.

        Returns:
            Dictionary with DATABASE_URL and other connection parameters

        Note: This always returns localhost as the host. For Docker deployments,
        the Docker deployer transforms localhost → host.docker.internal when
        generating docker-compose.yml. This ensures native apps work correctly
        while Docker apps get the right host after transformation.
        """
        admin = self._get_admin()
        password = self._get_stored_password()

        if not password:
            msg = (
                f"No stored password for addon '{self.addon_name}'. "
                "Run 'addons:create' first."
            )
            raise RuntimeError(msg)

        # Always use localhost - Docker deployer transforms this for containers
        app_host = "localhost"

        return {
            "DATABASE_URL": (
                f"postgresql://{self.db_user}:{password}@{app_host}:{admin.port}/{self.db_name}"
            ),
            "PGDATABASE": self.db_name,
            "PGUSER": self.db_user,
            "PGPASSWORD": password,
            "PGHOST": app_host,
            "PGPORT": str(admin.port),
        }

    def backup(self) -> Path:
        """Create a backup of the PostgreSQL database using pg_dump.

        Returns:
            Path to the backup file
        """
        admin = self._get_admin()
        password = self._get_stored_password()

        if not password:
            msg = f"No stored password for addon '{self.addon_name}'."
            raise RuntimeError(msg)

        backup_dir = HOP3_ROOT / "backups" / "postgres"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{self.addon_name}_{timestamp}.sql"

        # Use pg_dump to create backup
        cmd = [
            "pg_dump",
            "-h",
            admin.host,
            "-p",
            str(admin.port),
            "-U",
            self.db_user,
            "-d",
            self.db_name,
            "-f",
            str(backup_file),
        ]

        # Preserve existing environment and add PGPASSWORD
        env = os.environ.copy()
        env["PGPASSWORD"] = password
        subprocess.run(cmd, check=True, env=env)

        return backup_file

    def restore(self, backup_path: Path) -> None:
        """Restore PostgreSQL database from a backup file.

        Args:
            backup_path: Path to the SQL backup file
        """
        if not backup_path.exists():
            msg = f"Backup file not found: {backup_path}"
            raise FileNotFoundError(msg)

        admin = self._get_admin()
        password = self._get_stored_password()

        if not password:
            msg = f"No stored password for addon '{self.addon_name}'."
            raise RuntimeError(msg)

        # Use psql to restore
        cmd = [
            "psql",
            "-h",
            admin.host,
            "-p",
            str(admin.port),
            "-U",
            self.db_user,
            "-d",
            self.db_name,
            "-f",
            str(backup_path),
        ]

        # Preserve existing environment and add PGPASSWORD
        env = os.environ.copy()
        env["PGPASSWORD"] = password
        subprocess.run(cmd, check=True, env=env)

    def info(self) -> dict[str, Any]:
        """Get information about the PostgreSQL service.

        Returns:
            Dictionary with service details
        """
        admin = self._get_admin()
        password = self._get_stored_password()

        if not password:
            return {
                "addon_name": self.addon_name,
                "type": "postgres",
                "status": "not_created",
                "message": "Addon has not been created yet.",
            }

        connection = None
        try:
            connection = psycopg2.connect(
                host=admin.host,
                port=admin.port,
                user=self.db_user,
                password=password,
                dbname=self.db_name,
            )

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
                "host": admin.host,
                "port": admin.port,
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


# Backwards compatibility alias
PostgresqlAddon = PostgresAddon
