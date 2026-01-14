# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""MySQL service implementation.

This module implements the Addon protocol for MySQL,
allowing applications to create, attach, and manage MySQL databases.

Admin credentials are configured via environment variables:
- MYSQL_HOST (default: localhost)
- MYSQL_PORT (default: 3306)
- MYSQL_SUPERUSER (default: root)
- MYSQL_SUPERUSER_PASSWORD (required for most setups)

Addon passwords are stored persistently in HOP3_ROOT/addons/mysql/
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import mysql.connector
from mysql.connector import errorcode

from hop3.config import HOP3_ROOT

from .admin import MySQLAdmin


def _get_addon_secrets_dir() -> Path:
    """Get the directory for storing addon secrets."""
    secrets_dir = HOP3_ROOT / "addons" / "mysql"
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
class MySQLAddon:
    """MySQL service implementation using Addon protocol.

    This service manages MySQL database instances. Each service instance
    creates a dedicated database and user for isolation.

    Attributes:
        addon_name: The unique name for this MySQL service instance
    """

    # Class attribute for the strategy name
    name: str = "mysql"

    # Instance attributes
    addon_name: str = ""

    def __post_init__(self):
        """Validate that addon_name is provided."""
        if not self.addon_name:
            msg = "addon_name is required for MySQLAddon"
            raise ValueError(msg)

    @property
    def db_name(self) -> str:
        """Database name derived from service name."""
        # Replace hyphens with underscores for valid MySQL identifiers
        return self.addon_name.replace("-", "_")

    @property
    def db_user(self) -> str:
        """Database user name derived from service name."""
        # MySQL username has a 32-character limit, truncate if necessary
        user = f"{self.db_name}_user"
        return user[:32]

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

    def _get_admin(self) -> MySQLAdmin:
        """Get MySQL admin connection configuration."""
        return MySQLAdmin.from_config()

    def _get_stored_password(self) -> str | None:
        """Get the stored password for this addon, if any."""
        secrets_data = _load_addon_secrets(self.addon_name)
        if secrets_data:
            return secrets_data.get("password")
        return None

    def create(self) -> None:
        """Create a new MySQL database if it does not already exist.

        This method:
        1. Connects to MySQL as admin user
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
        cursor = None
        try:
            connection = mysql.connector.connect(**admin.get_connection_params())
            cursor = connection.cursor()

            # Check if database already exists
            cursor.execute(
                "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
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
                # User may or may not exist, so try CREATE first, fall back to ALTER
                try:
                    cursor.execute(
                        "CREATE USER %s@'%%' IDENTIFIED BY %s",
                        (self.db_user, password),
                    )
                except mysql.connector.Error as err:
                    if err.errno == errorcode.ER_CANNOT_USER:
                        # User exists, update password
                        cursor.execute(
                            "ALTER USER %s@'%%' IDENTIFIED BY %s",
                            (self.db_user, password),
                        )
                    else:
                        raise
            else:
                # Create user (ignore if already exists)
                try:
                    cursor.execute(
                        "CREATE USER %s@'%%' IDENTIFIED BY %s",
                        (self.db_user, password),
                    )
                except mysql.connector.Error as err:
                    if err.errno == errorcode.ER_CANNOT_USER:
                        # User already exists, update password
                        cursor.execute(
                            "ALTER USER %s@'%%' IDENTIFIED BY %s",
                            (self.db_user, password),
                        )
                    else:
                        raise

                # Create database
                cursor.execute(
                    f"CREATE DATABASE `{self.db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )

                # Grant privileges to user on the database
                grant_sql = f"GRANT ALL PRIVILEGES ON `{self.db_name}`.* TO %s@'%%'"
                cursor.execute(grant_sql, (self.db_user,))
                cursor.execute("FLUSH PRIVILEGES")

            connection.commit()

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
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def destroy(self) -> None:
        """Destroy the MySQL database and user.

        This permanently deletes all data. Use with caution.
        """
        admin = self._get_admin()

        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(**admin.get_connection_params())
            cursor = connection.cursor()

            # Drop database
            cursor.execute(f"DROP DATABASE IF EXISTS `{self.db_name}`")

            # Drop user
            try:
                drop_user_sql = "DROP USER IF EXISTS %s@'%%'"
                cursor.execute(drop_user_sql, (self.db_user,))
            except mysql.connector.Error:
                # User might not exist, that's okay
                pass

            connection.commit()

            # Delete stored secrets
            _delete_addon_secrets(self.addon_name)

        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_connection_details(self) -> dict[str, str]:
        """Get environment variables for connecting to this MySQL database.

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
                f"mysql://{self.db_user}:{password}@{app_host}:{admin.port}/{self.db_name}"
            ),
            "MYSQL_DATABASE": self.db_name,
            "MYSQL_USER": self.db_user,
            "MYSQL_PASSWORD": password,
            "MYSQL_HOST": app_host,
            "MYSQL_PORT": str(admin.port),
        }

    def backup(self) -> Path:
        """Create a backup of the MySQL database using mysqldump.

        Returns:
            Path to the backup file
        """
        admin = self._get_admin()
        password = self._get_stored_password()

        if not password:
            msg = f"No stored password for addon '{self.addon_name}'."
            raise RuntimeError(msg)

        backup_dir = HOP3_ROOT / "backups" / "mysql"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{self.addon_name}_{timestamp}.sql"

        # Use mysqldump to create backup
        cmd = [
            "mysqldump",
            "-h",
            admin.host,
            "-P",
            str(admin.port),
            "-u",
            self.db_user,
            f"-p{password}",
            "--single-transaction",
            "--routines",
            "--triggers",
            self.db_name,
        ]

        with Path(backup_file).open("w") as f:
            # Preserve existing environment
            env = os.environ.copy()
            subprocess.run(cmd, check=True, stdout=f, env=env)

        return backup_file

    def restore(self, backup_path: Path) -> None:
        """Restore MySQL database from a backup file.

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

        # Use mysql to restore
        cmd = [
            "mysql",
            "-h",
            admin.host,
            "-P",
            str(admin.port),
            "-u",
            self.db_user,
            f"-p{password}",
            self.db_name,
        ]

        with Path(backup_path).open() as f:
            # Preserve existing environment
            env = os.environ.copy()
            subprocess.run(cmd, check=True, stdin=f, env=env)

    def info(self) -> dict[str, Any]:
        """Get information about the MySQL service.

        Returns:
            Dictionary with service details
        """
        admin = self._get_admin()
        password = self._get_stored_password()

        if not password:
            return {
                "addon_name": self.addon_name,
                "type": "mysql",
                "status": "not_created",
                "message": "Addon has not been created yet.",
            }

        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=admin.host,
                port=admin.port,
                user=self.db_user,
                password=password,
                database=self.db_name,
            )
            cursor = connection.cursor()

            # Get database size
            cursor.execute(
                """
                SELECT SUM(data_length + index_length) as size
                FROM information_schema.TABLES
                WHERE table_schema = %s
                """,
                (self.db_name,),
            )
            result = cursor.fetchone()
            size_bytes: int = 0
            if result and isinstance(result, tuple) and result[0]:
                size_bytes = cast("int", result[0])

            # Get table count
            cursor.execute(
                """
                SELECT COUNT(*) FROM information_schema.TABLES
                WHERE table_schema = %s
                """,
                (self.db_name,),
            )
            table_result = cursor.fetchone()
            table_count: int = 0
            if table_result and isinstance(table_result, tuple):
                table_count = cast("int", table_result[0])

            # Get MySQL version
            cursor.execute("SELECT VERSION()")
            version_result = cursor.fetchone()
            version: str = ""
            if version_result and isinstance(version_result, tuple):
                version = cast("str", version_result[0])

            return {
                "addon_name": self.addon_name,
                "type": "mysql",
                "database": self.db_name,
                "user": self.db_user,
                "host": admin.host,
                "port": admin.port,
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2) if size_bytes else 0,
                "table_count": table_count,
                "version": version,
            }

        except mysql.connector.Error as e:
            return {
                "addon_name": self.addon_name,
                "type": "mysql",
                "status": "error",
                "error": str(e),
            }
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()


# Backwards compatibility alias
MysqlAddon = MySQLAddon
