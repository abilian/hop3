# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
MySQL service implementation.

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

import contextlib
import os
import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import mysql.connector
from mysql.connector import errorcode

from hop3.config import HOP3_ROOT
from hop3.core.identifiers import validate_service_name
from hop3.plugins.addons import (
    delete_addon_secrets,
    load_addon_secrets,
    save_addon_secrets,
)

from .admin import MySQLAdmin

if TYPE_CHECKING:
    from mysql.connector.abstracts import (
        MySQLConnectionAbstract,
        MySQLCursorAbstract,
    )
    from mysql.connector.pooling import PooledMySQLConnection

    # mysql.connector.connect() returns either a pooled or a direct connection.
    MySQLConnection = PooledMySQLConnection | MySQLConnectionAbstract

# Addon type identifier for secrets storage
ADDON_TYPE = "mysql"

# Hosts a per-app DB user may connect from. Native Hop3 apps come from
# localhost/127.0.0.1; Docker apps come from a container IP that depends on
# which pool Docker drew the network from — its default-address-pools span
# *both* 172.16.0.0/12 AND 192.168.0.0/16 (compose projects routinely land in
# 192.168.x), and custom networks may use 10.x. MySQL host patterns can't do
# CIDR, so we enumerate the RFC1918 wildcards. They only match private-source
# connections, so this does not expose the user to the public interface.
# (Granting only 172.% — the previous value — failed every compose app whose
# network came from the 192.168.x pool: "[1130] Host '192.168.x.y' is not
# allowed to connect to this MySQL server".)
ADDON_USER_HOSTS = ("localhost", "127.0.0.1", "10.%", "172.%", "192.168.%")


@dataclass(frozen=True)
class MySQLAddon:
    """
    MySQL service implementation using Addon protocol.

    This service manages MySQL database instances. Each service instance
    creates a dedicated database and user for isolation.

    Attributes:
        addon_name: The unique name for this MySQL service instance
    """

    # Class attribute for the strategy name
    name: str = "mysql"

    # Instance attributes
    addon_name: str = ""

    def __post_init__(self) -> None:
        """
        Validate that addon_name is provided and is a safe identifier.

        Defense in depth: the command boundary (AddonCreateCmd) already calls
        validate_service_name, but db_name flows into raw SQL identifier
        interpolation (CREATE DATABASE / GRANT) where parameter binding is
        not available, so re-check here before any plugin method runs.
        """
        if not self.addon_name:
            msg = "addon_name is required for MySQLAddon"
            raise ValueError(msg)
        validate_service_name(self.addon_name)

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
        """
        Get the password for the database user.

        Returns the stored password if available, or generates a new one.
        """
        stored_secrets = load_addon_secrets(ADDON_TYPE, self.addon_name)
        if stored_secrets and "password" in stored_secrets:
            return stored_secrets["password"]
        # Generate new password (will be stored during create())
        return secrets.token_urlsafe(32)

    def _get_admin(self) -> MySQLAdmin:
        """Get MySQL admin connection configuration."""
        return MySQLAdmin.from_config()

    def _create_or_update_user(
        self, cursor: MySQLCursorAbstract, host: str, password: str
    ) -> None:
        """
        Create ``<db_user>@<host>`` with the given password.

        If the row already exists, ALTER its password instead.
        """
        try:
            cursor.execute(
                "CREATE USER %s@%s IDENTIFIED BY %s",
                (self.db_user, host, password),
            )
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_CANNOT_USER:
                cursor.execute(
                    "ALTER USER %s@%s IDENTIFIED BY %s",
                    (self.db_user, host, password),
                )
            else:
                raise

    def _get_stored_password(self) -> str | None:
        """Get the stored password for this addon, if any."""
        secrets_data = load_addon_secrets(ADDON_TYPE, self.addon_name)
        if secrets_data:
            return secrets_data.get("password")
        return None

    def create(self) -> None:
        """
        Create a new MySQL database if it does not already exist.

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
            existing_secrets = load_addon_secrets(ADDON_TYPE, self.addon_name)

            if db_exists and existing_secrets:
                # Database and secrets both exist - nothing to do
                return

            # A database that exists WITHOUT our secrets is not ours: it outlived
            # the app it belonged to (a server rebuild reclaims Hop3's own state
            # but not MySQL's, which is a separate service). Adopting it silently
            # hands a brand-new app the previous one's tables — including its
            # user accounts — and then breaks the new app's installer on the
            # rows it did not expect. Refuse, and say exactly how to proceed.
            if db_exists and not existing_secrets:
                _refuse_foreign_database(cursor, self.db_name, self.addon_name)

            # Create a user row per host the addon is reached from (native +
            # every Docker network pool). See ADDON_USER_HOSTS for the why.
            hosts = ADDON_USER_HOSTS

            for host in hosts:
                self._create_or_update_user(cursor, host, password)

            if not db_exists:
                cursor.execute(
                    f"CREATE DATABASE `{self.db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )

            for host in hosts:
                cursor.execute(
                    f"GRANT ALL PRIVILEGES ON `{self.db_name}`.* TO %s@%s",
                    (self.db_user, host),
                )
            cursor.execute("FLUSH PRIVILEGES")

            connection.commit()

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
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def destroy(self) -> None:
        """
        Destroy the MySQL database and user.

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

            # Drop user rows for every host we created (see ensure_exists)
            for host in ADDON_USER_HOSTS:
                with contextlib.suppress(mysql.connector.Error):
                    cursor.execute("DROP USER IF EXISTS %s@%s", (self.db_user, host))

            connection.commit()

            # Delete stored secrets
            delete_addon_secrets(ADDON_TYPE, self.addon_name)

        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_connection_details(self) -> dict[str, str]:
        """
        Get environment variables for connecting to this MySQL database.

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
        # issues (some runtimes resolve localhost to ::1 first, but MySQL/MariaDB
        # typically only listens on 127.0.0.1).
        # Docker deployer transforms 127.0.0.1 → host.docker.internal for containers.
        app_host = "127.0.0.1"

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

    @staticmethod
    def _exec(connection: MySQLConnection, statement: str) -> dict:
        """Run a statement on a connection; shape rows or a status message."""
        try:
            cursor = connection.cursor()
            cursor.execute(statement)
            if cursor.description is not None:
                columns = [col[0] for col in cursor.description]
                rows = [list(row) for row in cursor.fetchall()]
                cursor.close()
                return {"columns": columns, "rows": rows}
            connection.commit()
            message = f"OK ({cursor.rowcount} row(s) affected)"
            cursor.close()
            return {"message": message}
        finally:
            connection.close()

    def run_sql(self, statement: str) -> dict:
        """
        Run an ad-hoc SQL statement as the addon's own (app) user.

        Connects with the app-level credentials (not the superuser), so the
        statement is confined to this addon's database. The password travels
        in-process via mysql.connector (never on a command line).

        Returns:
            ``{"columns": [...], "rows": [[...]]}`` for a result set, or
            ``{"message": "..."}`` for a statement that returns no rows.
        """
        details = self.get_connection_details()
        connection = mysql.connector.connect(
            host=details["MYSQL_HOST"],
            port=int(details["MYSQL_PORT"]),
            user=details["MYSQL_USER"],
            password=details["MYSQL_PASSWORD"],
            database=details["MYSQL_DATABASE"],
        )
        return self._exec(connection, statement)

    def run_admin_sql(self, statement: str) -> dict:
        """
        Run SQL on this addon's database as the superuser.

        For diagnostics (information_schema.processlist, global variables, …)
        that the per-app user can't see in full. Internal use only — callers
        pass canned queries, never user input (use run_sql for that).
        """
        admin = self._get_admin()
        connection = mysql.connector.connect(
            **admin.get_connection_params(database=self.db_name)
        )
        return self._exec(connection, statement)

    def exists(self) -> bool:
        """Return True if this addon's database exists."""
        admin = self._get_admin()
        connection = mysql.connector.connect(**admin.get_connection_params())
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
                "WHERE SCHEMA_NAME = %s",
                (self.db_name,),
            )
            found = cursor.fetchone() is not None
            cursor.close()
            return found
        finally:
            connection.close()

    def backup(self) -> Path:
        """
        Create a backup of the MySQL database using mysqldump.

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

        # SECURITY: pass the password via MYSQL_PWD instead of -p{password}
        # so it doesn't appear in /proc/<pid>/cmdline (visible to other
        # local users for the duration of the dump). MYSQL_PWD is the
        # documented mechanism for this; the surrounding env is otherwise
        # preserved.
        cmd = [
            "mysqldump",
            "-h",
            admin.host,
            "-P",
            str(admin.port),
            "-u",
            self.db_user,
            "--single-transaction",
            "--routines",
            "--triggers",
            self.db_name,
        ]

        with Path(backup_file).open("w") as f:
            env = os.environ.copy()
            env["MYSQL_PWD"] = password
            subprocess.run(cmd, check=True, stdout=f, env=env)

        return backup_file

    def restore(self, backup_path: Path) -> None:
        """
        Restore MySQL database from a backup file.

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

        # SECURITY: see backup() above — MYSQL_PWD avoids leaking the
        # password through argv.
        cmd = [
            "mysql",
            "-h",
            admin.host,
            "-P",
            str(admin.port),
            "-u",
            self.db_user,
            self.db_name,
        ]

        with Path(backup_path).open() as f:
            env = os.environ.copy()
            env["MYSQL_PWD"] = password
            subprocess.run(cmd, check=True, stdin=f, env=env)

    def info(self) -> dict[str, Any]:
        """
        Get information about the MySQL service.

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


def _refuse_foreign_database(
    cursor: MySQLCursorAbstract, db_name: str, addon_name: str
) -> None:
    """
    Abort when the target database exists but holds data we did not provision.

    An EMPTY leftover is harmless and is adopted silently — that is the common
    case after a partial teardown, and failing on it would be noise. A populated
    one is different: its contents belong to a previous app of the same name.
    """
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
        (db_name,),
    )
    row = cursor.fetchone()
    table_count = row[0] if row else 0
    if not table_count:
        return  # empty leftover: safe to reuse

    msg = (
        f"Database '{db_name}' already exists with {table_count} table(s), but "
        f"Hop3 holds no credentials for addon '{addon_name}' — so this data is "
        f"left over from a previous app of the same name, not this one. "
        f"Refusing to attach it: the new app would inherit the old app's data "
        f"(including its user accounts), and its installer would fail on rows it "
        f"did not create. Either drop it "
        f'(mysql -e "DROP DATABASE \\`{db_name}\\`") if the data is no longer '
        f"wanted, or install this app under a different name."
    )
    raise RuntimeError(msg)
