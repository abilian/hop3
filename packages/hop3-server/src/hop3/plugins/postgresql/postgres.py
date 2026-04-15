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

import os
import re
import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.errors import DuplicateObject  # type: ignore[import-not-found]
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from hop3.config import HOP3_ROOT
from hop3.lib.logging import server_log
from hop3.plugins.addons import (
    delete_addon_secrets,
    load_addon_secrets,
    save_addon_secrets,
)

from .admin import PostgresAdmin

# Addon type identifier for secrets storage
ADDON_TYPE = "postgres"


def _find_pg_hba() -> Path | None:
    """Find pg_hba.conf across different Linux distributions.

    Returns:
        Path to pg_hba.conf, or None if not found.
    """
    # Debian/Ubuntu: /etc/postgresql/<version>/main/pg_hba.conf
    debian_base = Path("/etc/postgresql")
    if debian_base.exists():
        for version_dir in sorted(debian_base.iterdir(), reverse=True):
            candidate = version_dir / "main" / "pg_hba.conf"
            if candidate.exists():
                return candidate

    # Fedora/RHEL: /var/lib/pgsql/data/pg_hba.conf
    fedora_conf = Path("/var/lib/pgsql/data/pg_hba.conf")
    if fedora_conf.exists():
        return fedora_conf

    return None


def _ensure_pg_hba_docker_access() -> None:
    """Ensure pg_hba.conf allows connections from Docker networks.

    This is called when provisioning a PostgreSQL addon to ensure Docker
    containers can connect. The configuration is idempotent.

    Raises:
        FileNotFoundError: If pg_hba.conf cannot be found.
        PermissionError: If pg_hba.conf cannot be modified.
    """
    pg_hba = _find_pg_hba()
    if not pg_hba:
        msg = "pg_hba.conf not found"
        raise FileNotFoundError(msg)

    content = pg_hba.read_text()

    # Docker network range covering all typical Docker networks
    docker_network = "172.16.0.0/12"

    if docker_network in content:
        return  # Already configured

    # Add entry for Docker networks (allow all users with md5 auth)
    hba_entry = f"\n# Allow Docker containers to connect (Hop3)\nhost    all    all    {docker_network}    md5\n"
    content += hba_entry

    pg_hba.write_text(content)
    server_log.info(f"Added pg_hba.conf entry for Docker networks: {docker_network}")

    # Reload PostgreSQL to apply changes
    subprocess.run(
        ["sudo", "-n", "systemctl", "reload", "postgresql"],
        check=False,
        capture_output=True,
    )


def _find_pg_conf() -> Path | None:
    """Find postgresql.conf across different Linux distributions.

    Returns:
        Path to postgresql.conf, or None if not found.
    """
    # Debian/Ubuntu: /etc/postgresql/<version>/main/postgresql.conf
    debian_base = Path("/etc/postgresql")
    if debian_base.exists():
        for version_dir in sorted(debian_base.iterdir(), reverse=True):
            candidate = version_dir / "main" / "postgresql.conf"
            if candidate.exists():
                return candidate

    # Fedora/RHEL: /var/lib/pgsql/data/postgresql.conf
    fedora_conf = Path("/var/lib/pgsql/data/postgresql.conf")
    if fedora_conf.exists():
        return fedora_conf

    return None


def _ensure_pg_listen_addresses() -> None:
    """Ensure PostgreSQL listens on all interfaces for Docker access.

    Raises:
        FileNotFoundError: If postgresql.conf cannot be found.
        PermissionError: If postgresql.conf cannot be modified.
    """
    pg_conf = _find_pg_conf()
    if not pg_conf:
        msg = "postgresql.conf not found"
        raise FileNotFoundError(msg)

    content = pg_conf.read_text()

    if "listen_addresses = '*'" in content:
        return  # Already configured

    # Update listen_addresses
    if re.search(r"^#?\s*listen_addresses\s*=", content, re.MULTILINE):
        content = re.sub(
            r"^#?\s*listen_addresses\s*=\s*'[^']*'",
            "listen_addresses = '*'",
            content,
            flags=re.MULTILINE,
        )
    else:
        content = f"listen_addresses = '*'\n{content}"

    pg_conf.write_text(content)
    server_log.info("Updated PostgreSQL listen_addresses to '*'")

    # Restart PostgreSQL (listen_addresses requires restart, not reload)
    subprocess.run(
        ["sudo", "-n", "systemctl", "restart", "postgresql"],
        check=False,
        capture_output=True,
    )


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
        stored_secrets = load_addon_secrets(ADDON_TYPE, self.addon_name)
        if stored_secrets and "password" in stored_secrets:
            return stored_secrets["password"]
        # Generate new password (will be stored during create())
        return secrets.token_urlsafe(32)

    def _get_admin(self) -> PostgresAdmin:
        """Get PostgreSQL admin connection configuration."""
        return PostgresAdmin.from_config()

    def _get_stored_password(self) -> str | None:
        """Get the stored password for this addon, if any."""
        secrets = load_addon_secrets(ADDON_TYPE, self.addon_name)
        if secrets:
            return secrets.get("password")
        return None

    def create(self) -> None:
        """Create a new PostgreSQL database if it does not already exist.

        This method:
        1. Ensures PostgreSQL is configured for Docker access
        2. Connects to PostgreSQL as admin user
        3. Creates a new database user with a secure password
        4. Creates a new database owned by that user
        5. Stores the password for future use

        If the database already exists but secrets are missing (e.g., after
        server reinstall), the password is regenerated and saved.
        """
        # Ensure PostgreSQL is configured for Docker container access
        # This is idempotent and only makes changes if needed
        # These may fail if PostgreSQL is remote or we lack permissions - that's OK
        try:
            _ensure_pg_hba_docker_access()
            _ensure_pg_listen_addresses()
        except (FileNotFoundError, PermissionError) as e:
            server_log.debug(f"Skipping local PostgreSQL configuration: {e}")

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
                existing_secrets = load_addon_secrets(ADDON_TYPE, self.addon_name)

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
            save_addon_secrets(
                ADDON_TYPE,
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

    def exists(self) -> bool:
        """Check if this PostgreSQL database exists.

        Returns:
            True if the database exists, False otherwise.
        """
        admin = self._get_admin()

        connection = None
        try:
            connection = psycopg2.connect(**admin.get_connection_params())
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (self.db_name,),
                )
                return cursor.fetchone() is not None
        except Exception:
            return False
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
            delete_addon_secrets(ADDON_TYPE, self.addon_name)

        finally:
            if connection:
                connection.close()

    def get_connection_details(self) -> dict[str, str]:
        """Get environment variables for connecting to this PostgreSQL database.

        Returns:
            Dictionary with DATABASE_URL and other connection parameters

        Note: This always returns 127.0.0.1 as the host (not "localhost") to
        avoid IPv6 resolution issues. For Docker deployments, the Docker deployer
        transforms 127.0.0.1 → host.docker.internal when generating
        docker-compose.yml.
        """
        admin = self._get_admin()
        password = self._get_stored_password()

        if not password:
            msg = (
                f"No stored password for addon '{self.addon_name}'. "
                "Run 'addons create' first."
            )
            raise RuntimeError(msg)

        # Always use 127.0.0.1 instead of "localhost" to avoid IPv6 resolution
        # issues (some runtimes resolve localhost to ::1 first, but PostgreSQL
        # may only listen on 127.0.0.1).
        # Docker deployer transforms 127.0.0.1 → host.docker.internal for containers.
        app_host = "127.0.0.1"

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
                # Get database size (aggregate always returns one row)
                cursor.execute(
                    "SELECT pg_database_size(%s);",
                    (self.db_name,),
                )
                row = cursor.fetchone()
                assert row is not None  # aggregate always returns one row
                size_bytes = row[0]

                # Get table count (aggregate always returns one row)
                cursor.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public';"
                )
                row = cursor.fetchone()
                assert row is not None  # aggregate always returns one row
                table_count = row[0]

                # Get PostgreSQL version (always returns one row)
                cursor.execute("SELECT version();")
                row = cursor.fetchone()
                assert row is not None  # version() always returns one row
                version = row[0]

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
