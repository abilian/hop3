# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for MySQL addon.

These tests run against a real MySQL instance and verify actual
database operations (create, destroy, backup, restore, info).

Requirements:
- MySQL must be installed and running
- Admin credentials must be configured via:
  - MYSQL_ADMIN_URL=mysql://user:pass@host:port/db, or
  - MYSQL_HOST, MYSQL_PORT, MYSQL_SUPERUSER, MYSQL_SUPERUSER_PASSWORD
- These tests are skipped if MySQL is not available

Run with: pytest tests/b_integration/plugins/test_mysql_integration.py -v
"""

from __future__ import annotations

import shutil
import uuid
from contextlib import suppress

import mysql.connector
import pytest

import hop3.plugins.mysql.mysql as mysql_module
from hop3.plugins.mysql.admin import MySQLAdmin
from hop3.plugins.mysql.mysql import MySQLAddon


def mysql_available() -> bool:
    """Check if MySQL is available for testing.

    Tries to connect using configured admin credentials.
    """
    try:
        admin = MySQLAdmin.from_config()
        conn = mysql.connector.connect(**admin.get_connection_params())
        conn.close()
        return True
    except mysql.connector.Error:
        return False


# Skip all tests in this module if MySQL is not available
pytestmark = pytest.mark.skipif(
    not mysql_available(),
    reason="MySQL not available (check MYSQL_ADMIN_URL or MYSQL_* config)",
)


@pytest.fixture
def admin():
    """Get MySQL admin connection."""
    return MySQLAdmin.from_config()


@pytest.fixture
def unique_addon_name():
    """Generate a unique addon name for test isolation."""
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def mysql_addon(unique_addon_name):
    """Create a MySQLAddon and clean up after test."""
    addon = MySQLAddon(addon_name=unique_addon_name)
    yield addon
    # Cleanup: try to destroy even if test failed
    # Already destroyed or never created
    with suppress(RuntimeError, mysql.connector.Error):
        addon.destroy()


def _database_exists(admin: MySQLAdmin, db_name: str) -> bool:
    """Check if a database exists using admin connection."""
    conn = mysql.connector.connect(**admin.get_connection_params())
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
            (db_name,),
        )
        return cursor.fetchone() is not None
    finally:
        if cursor:
            cursor.close()
        conn.close()


def _user_exists(admin: MySQLAdmin, username: str) -> bool:
    """Check if a user exists using admin connection.

    With the per-host grants pattern (W16 MySQL addon fix), a single
    logical user has multiple rows in ``mysql.user`` — one per host
    (``@'localhost'``, ``@'127.0.0.1'``, ``@'172.%'``). We must consume
    all of them before closing the cursor, otherwise mysql-connector
    raises ``InternalError: Unread result found``.
    """
    conn = mysql.connector.connect(**admin.get_connection_params())
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT User FROM mysql.user WHERE User = %s",
            (username,),
        )
        rows = cursor.fetchall()
        return len(rows) > 0
    finally:
        if cursor:
            cursor.close()
        conn.close()


class TestMySQLCreate:
    """Tests for database creation."""

    def test_create_database(self, mysql_addon, admin):
        """Test that create() actually creates a MySQL database."""
        mysql_addon.create()

        # Verify database exists
        assert _database_exists(admin, mysql_addon.db_name), "Database was not created"

        # Verify user exists
        assert _user_exists(admin, mysql_addon.db_user), "User was not created"

    def test_create_is_idempotent(self, mysql_addon, admin):
        """Test that calling create() twice doesn't fail."""
        mysql_addon.create()
        mysql_addon.create()  # Should not raise

        # Database should still exist
        assert _database_exists(admin, mysql_addon.db_name)


class TestMySQLDestroy:
    """Tests for database destruction."""

    def test_destroy_database(self, mysql_addon, admin):
        """Test that destroy() removes the database and user."""
        mysql_addon.create()
        mysql_addon.destroy()

        # Verify database is gone
        assert not _database_exists(admin, mysql_addon.db_name), (
            "Database was not destroyed"
        )

        # Verify user is gone
        assert not _user_exists(admin, mysql_addon.db_user), "User was not destroyed"


class TestMySQLConnectionDetails:
    """Tests for connection details."""

    def test_get_connection_details(self, mysql_addon):
        """Test that connection details allow actual database connection."""
        mysql_addon.create()
        details = mysql_addon.get_connection_details()

        # Verify all expected keys
        assert "DATABASE_URL" in details
        assert "MYSQL_DATABASE" in details
        assert "MYSQL_USER" in details
        assert "MYSQL_PASSWORD" in details
        assert "MYSQL_HOST" in details
        assert "MYSQL_PORT" in details

        # Verify we can connect with these credentials
        conn = mysql.connector.connect(
            host=details["MYSQL_HOST"],
            port=int(details["MYSQL_PORT"]),
            user=details["MYSQL_USER"],
            password=details["MYSQL_PASSWORD"],
            database=details["MYSQL_DATABASE"],
        )
        conn.close()


class TestMySQLInfo:
    """Tests for database info."""

    def test_info_returns_details(self, mysql_addon):
        """Test that info() returns actual database information."""
        mysql_addon.create()
        info = mysql_addon.info()

        assert info["addon_name"] == mysql_addon.addon_name
        assert info["type"] == "mysql"
        assert info["database"] == mysql_addon.db_name
        assert "size_bytes" in info
        assert "table_count" in info
        assert "version" in info


@pytest.mark.skipif(
    shutil.which("mysqldump") is None,
    reason="mysqldump not found in PATH (MySQL client tools required)",
)
class TestMySQLBackupRestore:
    """Tests for backup and restore."""

    def test_backup_creates_file(self, mysql_addon, tmp_path):
        """Test that backup creates an actual SQL file."""
        # Temporarily override HOP3_ROOT for test
        original_root = mysql_module.HOP3_ROOT
        mysql_module.HOP3_ROOT = tmp_path

        try:
            mysql_addon.create()

            # Create a table with some data
            details = mysql_addon.get_connection_details()
            conn = mysql.connector.connect(
                host=details["MYSQL_HOST"],
                port=int(details["MYSQL_PORT"]),
                user=details["MYSQL_USER"],
                password=details["MYSQL_PASSWORD"],
                database=details["MYSQL_DATABASE"],
            )
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE test_data (id INT AUTO_INCREMENT PRIMARY KEY, value VARCHAR(255))"
            )
            cursor.execute("INSERT INTO test_data (value) VALUES ('hello')")
            conn.commit()
            cursor.close()
            conn.close()

            # Create backup
            backup_path = mysql_addon.backup()

            # Verify backup file exists and contains SQL
            assert backup_path.exists()
            content = backup_path.read_text()
            assert "CREATE TABLE" in content or "test_data" in content

        finally:
            mysql_module.HOP3_ROOT = original_root

    def test_restore_recovers_data(self, mysql_addon, tmp_path):
        """Test that restore actually recovers data."""
        original_root = mysql_module.HOP3_ROOT
        mysql_module.HOP3_ROOT = tmp_path

        try:
            mysql_addon.create()

            # Create data
            details = mysql_addon.get_connection_details()
            conn = mysql.connector.connect(
                host=details["MYSQL_HOST"],
                port=int(details["MYSQL_PORT"]),
                user=details["MYSQL_USER"],
                password=details["MYSQL_PASSWORD"],
                database=details["MYSQL_DATABASE"],
            )
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE test_data (id INT AUTO_INCREMENT PRIMARY KEY, value VARCHAR(255))"
            )
            cursor.execute("INSERT INTO test_data (value) VALUES ('original')")
            conn.commit()
            cursor.close()
            conn.close()

            # Backup
            backup_path = mysql_addon.backup()

            # Drop the table (simulate data loss)
            conn = mysql.connector.connect(
                host=details["MYSQL_HOST"],
                port=int(details["MYSQL_PORT"]),
                user=details["MYSQL_USER"],
                password=details["MYSQL_PASSWORD"],
                database=details["MYSQL_DATABASE"],
            )
            cursor = conn.cursor()
            cursor.execute("DROP TABLE test_data")
            conn.commit()
            cursor.close()
            conn.close()

            # Restore
            mysql_addon.restore(backup_path)

            # Verify data is back
            conn = mysql.connector.connect(
                host=details["MYSQL_HOST"],
                port=int(details["MYSQL_PORT"]),
                user=details["MYSQL_USER"],
                password=details["MYSQL_PASSWORD"],
                database=details["MYSQL_DATABASE"],
            )
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM test_data")
            result = cursor.fetchone()
            cursor.close()
            conn.close()

            assert result[0] == "original"

        finally:
            mysql_module.HOP3_ROOT = original_root
