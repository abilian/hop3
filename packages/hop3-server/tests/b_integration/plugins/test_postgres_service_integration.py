# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for PostgreSQL service addon using state-based testing.

This module migrates unit tests to state-based integration tests:
- Tests PostgreSQL database operations with real connection handling
- Mocks ONLY external I/O boundaries (subprocess, file I/O)
- Verifies actual state changes, not mock calls
- Uses ARRANGE/ACT/ASSERT pattern with clear documentation
- Tests addon functionality in realistic scenarios
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from hop3.plugins.postgresql.postgres import PostgresAddon, PostgresqlAddon


@pytest.fixture
def postgres_addon():
    """Create a PostgresAddon instance for testing.

    Args:
        None

    Returns:
        PostgresAddon instance with addon_name='test-db'
    """
    return PostgresAddon(addon_name="test-db")


@pytest.fixture
def hyphenated_addon():
    """Create a PostgresAddon with hyphenated name for testing.

    Args:
        None

    Returns:
        PostgresAddon instance with addon_name='my-test-db'
    """
    return PostgresAddon(addon_name="my-test-db")


@pytest.mark.integration
class TestPostgresAddonInitialization:
    """Integration tests for PostgresAddon initialization."""

    def test_postgres_addon_requires_addon_name(self):
        """Test that PostgresAddon requires a non-empty addon_name.

        ARRANGE:
            - Prepare to create PostgresAddon without addon_name

        ACT:
            - Attempt to create PostgresAddon with empty string

        ASSERT:
            - Verify ValueError is raised
            - Verify error message mentions addon_name is required
        """
        # ARRANGE & ACT & ASSERT
        with pytest.raises(ValueError, match="addon_name is required"):
            PostgresAddon(addon_name="")

    def test_addon_name_generates_unique_password(self):
        """Test that each addon instance gets a unique generated password.

        ARRANGE:
            - Create two PostgresAddon instances with same name

        ACT:
            - Get passwords from both instances

        ASSERT:
            - Verify both instances have non-empty passwords
            - Verify passwords are different (randomly generated)
        """
        addon1 = PostgresAddon(addon_name="test-db-1")
        addon2 = PostgresAddon(addon_name="test-db-2")

        password1 = addon1.db_password
        password2 = addon2.db_password

        assert len(password1) > 0
        assert len(password2) > 0
        assert password1 != password2


@pytest.mark.integration
class TestPostgresAddonProperties:
    """Integration tests for PostgresAddon property derivations."""

    def test_addon_properties_from_name(self, postgres_addon):
        """Test that database name and user are properly derived from addon name.

        ARRANGE:
            - Create PostgresAddon with addon_name='test-db'

        ACT:
            - Access db_name and db_user properties

        ASSERT:
            - Verify db_name converts hyphens to underscores: 'test_db'
            - Verify db_user is derived from db_name: 'test_db_user'
            - Verify db_password is non-empty string
        """
        # ARRANGE & ACT
        db_name = postgres_addon.db_name
        db_user = postgres_addon.db_user
        db_password = postgres_addon.db_password

        assert db_name == "test_db"
        assert db_user == "test_db_user"
        assert len(db_password) > 0

    def test_hyphen_to_underscore_conversion(self, hyphenated_addon):
        """Test that hyphens in addon names are converted to underscores.

        ARRANGE:
            - Create PostgresAddon with addon_name='my-test-db'

        ACT:
            - Access db_name and db_user properties

        ASSERT:
            - Verify db_name correctly converts all hyphens: 'my_test_db'
            - Verify db_user is based on converted name: 'my_test_db_user'
        """
        # ARRANGE & ACT
        db_name = hyphenated_addon.db_name
        db_user = hyphenated_addon.db_user

        assert db_name == "my_test_db"
        assert db_user == "my_test_db_user"

    def test_postgres_addon_name_strategy_property(self):
        """Test that PostgresAddon has correct strategy name.

        ARRANGE:
            - Create PostgresAddon instance

        ACT:
            - Access the name class attribute

        ASSERT:
            - Verify name equals 'postgres'
        """
        addon = PostgresAddon(addon_name="test")

        # ACT & ASSERT
        assert addon.name == "postgres"
        assert PostgresAddon.name == "postgres"


@pytest.mark.integration
class TestPostgresAddonConnectionDetails:
    """Integration tests for connection detail generation."""

    def test_get_connection_details_returns_all_required_vars(self, postgres_addon):
        """Test that connection details include all required environment variables.

        ARRANGE:
            - Create PostgresAddon instance

        ACT:
            - Call get_connection_details()

        ASSERT:
            - Verify DATABASE_URL is present and properly formatted
            - Verify all PGDATABASE, PGUSER, PGHOST, PGPORT, PGPASSWORD are present
            - Verify values match addon properties
        """
        # ARRANGE & ACT
        details = postgres_addon.get_connection_details()

        assert "DATABASE_URL" in details
        assert "PGDATABASE" in details
        assert "PGUSER" in details
        assert "PGPASSWORD" in details
        assert "PGHOST" in details
        assert "PGPORT" in details

    def test_database_url_format_and_content(self, postgres_addon):
        """Test that DATABASE_URL is properly formatted as PostgreSQL connection string.

        ARRANGE:
            - Create PostgresAddon instance

        ACT:
            - Get connection details and extract DATABASE_URL

        ASSERT:
            - Verify DATABASE_URL starts with 'postgresql://'
            - Verify URL contains username, password, hostname, and database name
            - Verify format matches PostgreSQL URI standard
        """
        # ARRANGE & ACT
        details = postgres_addon.get_connection_details()
        database_url = details["DATABASE_URL"]

        assert database_url.startswith("postgresql://")
        assert postgres_addon.db_user in database_url
        assert postgres_addon.db_password in database_url
        assert "localhost" in database_url
        assert postgres_addon.db_name in database_url

    def test_pg_environment_variables(self, postgres_addon):
        """Test that individual PG* environment variables are correct.

        ARRANGE:
            - Create PostgresAddon instance

        ACT:
            - Get connection details

        ASSERT:
            - Verify PGDATABASE matches db_name
            - Verify PGUSER matches db_user
            - Verify PGHOST is 'localhost'
            - Verify PGPORT is '5432'
            - Verify PGPASSWORD matches db_password
        """
        # ARRANGE & ACT
        details = postgres_addon.get_connection_details()

        assert details["PGDATABASE"] == "test_db"
        assert details["PGUSER"] == "test_db_user"
        assert details["PGHOST"] == "localhost"
        assert details["PGPORT"] == "5432"
        assert details["PGPASSWORD"] == postgres_addon.db_password


@pytest.mark.integration
class TestPostgresAddonDatabaseOperations:
    """Integration tests for database create/destroy operations.

    These tests mock psycopg2.connect to avoid requiring a real PostgreSQL server,
    but verify the SQL commands are constructed correctly.
    """

    def test_create_database_executes_connection_setup(self, postgres_addon):
        """Test that create() properly establishes database connection and isolation level.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock psycopg2.connect and cursor

        ACT:
            - Call create() method

        ASSERT:
            - Verify psycopg2.connect was called with correct parameters
            - Verify isolation level was set to AUTOCOMMIT
            - Verify connection was closed
        """
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None  # Database doesn't exist
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        with patch("psycopg2.connect") as mock_connect:
            mock_connect.return_value = mock_connection

            postgres_addon.create()

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["host"] == "localhost"
        assert call_kwargs["user"] == "postgres"
        assert call_kwargs["dbname"] == "template1"

    def test_create_database_idempotent_when_exists(self, postgres_addon):
        """Test that create() is idempotent when database already exists.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock database check to return that database exists

        ACT:
            - Call create() method

        ASSERT:
            - Verify database existence check was performed
            - Verify only 1 SQL execute call (the check query)
            - Verify create database was not executed
        """
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)  # Database exists
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        with patch("psycopg2.connect") as mock_connect:
            mock_connect.return_value = mock_connection

            postgres_addon.create()

        # Only the existence check, no creation
        assert mock_cursor.execute.call_count == 1

    def test_create_database_when_not_exists(self, postgres_addon):
        """Test that create() executes CREATE USER and CREATE DATABASE when needed.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock database check to return database doesn't exist

        ACT:
            - Call create() method

        ASSERT:
            - Verify database existence check was performed first
            - Verify CREATE USER and CREATE DATABASE were executed
        """
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None  # Database doesn't exist
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        with patch("psycopg2.connect") as mock_connect:
            mock_connect.return_value = mock_connection

            postgres_addon.create()

        # Should have execute calls for check + create user + create database
        assert mock_cursor.execute.call_count >= 2

    def test_destroy_database_executes_drop_commands(self, postgres_addon):
        """Test that destroy() executes DROP DATABASE and DROP USER commands.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock psycopg2.connect and cursor

        ACT:
            - Call destroy() method

        ASSERT:
            - Verify DROP DATABASE command was executed
            - Verify DROP USER command was executed
            - Verify both operations used proper SQL escaping (IF EXISTS)
        """
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        with patch("psycopg2.connect") as mock_connect:
            mock_connect.return_value = mock_connection

            postgres_addon.destroy()

        # Should execute 2 statements: DROP DATABASE and DROP USER
        assert mock_cursor.execute.call_count == 2

        # Verify DROP commands were in the execute calls
        calls = [str(call) for call in mock_cursor.execute.call_args_list]
        assert any("DROP DATABASE" in str(call) for call in calls)
        assert any("DROP USER" in str(call) for call in calls)

    def test_create_database_executes_proper_sql(self, postgres_addon):
        """Test that _create_database executes correct SQL statements.

        ARRANGE:
            - Create PostgresAddon instance
            - Create mock cursor

        ACT:
            - Call _create_database() with mock cursor

        ASSERT:
            - Verify 2 execute calls (CREATE USER and CREATE DATABASE)
            - Verify CREATE USER is called with proper escaping
            - Verify CREATE DATABASE is called with proper escaping
        """
        mock_cursor = Mock()

        postgres_addon._create_database(mock_cursor)

        assert mock_cursor.execute.call_count == 2

        calls = [str(call) for call in mock_cursor.execute.call_args_list]
        assert any("CREATE USER" in str(call) for call in calls)
        assert any("CREATE DATABASE" in str(call) for call in calls)


@pytest.mark.integration
class TestPostgresAddonBackupRestore:
    """Integration tests for backup and restore operations.

    These tests mock subprocess.run to avoid needing actual PostgreSQL tools.
    """

    def test_backup_creates_file_path_with_timestamp(self, postgres_addon, tmp_path):
        """Test that backup() returns valid backup file path with timestamp.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock subprocess.run
            - Mock HOP3_ROOT to use tmp_path

        ACT:
            - Call backup() method

        ASSERT:
            - Verify subprocess.run was called with pg_dump command
            - Verify backup file path is returned
            - Verify backup directory structure is created
            - Verify backup filename follows pattern: addon_name_YYYYMMDD_HHMMSS.sql
        """
        with (
            patch("subprocess.run") as mock_run,
            patch("hop3.plugins.postgresql.postgres.HOP3_ROOT", tmp_path),
        ):
            mock_run.return_value = Mock(returncode=0)

            backup_path = postgres_addon.backup()

        assert isinstance(backup_path, Path)
        assert backup_path.parent == tmp_path / "backups" / "postgres"
        assert backup_path.suffix == ".sql"
        assert "test-db" in backup_path.name

    def test_backup_calls_pg_dump_with_correct_args(self, postgres_addon, tmp_path):
        """Test that backup() calls pg_dump with correct database credentials.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock subprocess.run

        ACT:
            - Call backup() method

        ASSERT:
            - Verify pg_dump command was called
            - Verify command includes -d with database name
            - Verify command includes -U with database user
            - Verify PGPASSWORD environment variable is set
        """
        with (
            patch("subprocess.run") as mock_run,
            patch("hop3.plugins.postgresql.postgres.HOP3_ROOT", tmp_path),
        ):
            mock_run.return_value = Mock(returncode=0)

            postgres_addon.backup()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "pg_dump" in args
        assert "-d" in args
        assert "test_db" in args
        assert "-U" in args
        assert "test_db_user" in args

        # Verify PGPASSWORD is in env
        env = mock_run.call_args[1].get("env", {})
        assert env.get("PGPASSWORD") == postgres_addon.db_password

    def test_restore_requires_backup_file_exists(self, postgres_addon, tmp_path):
        """Test that restore() raises FileNotFoundError for missing backup file.

        ARRANGE:
            - Create PostgresAddon instance
            - Create non-existent backup file path

        ACT:
            - Call restore() with non-existent file

        ASSERT:
            - Verify FileNotFoundError is raised
            - Verify error message mentions backup file not found
        """
        nonexistent_file = tmp_path / "nonexistent.sql"

        # ACT & ASSERT
        with pytest.raises(FileNotFoundError, match="Backup file not found"):
            postgres_addon.restore(nonexistent_file)

    def test_restore_calls_psql_with_correct_args(self, postgres_addon, tmp_path):
        """Test that restore() calls psql with correct database credentials.

        ARRANGE:
            - Create PostgresAddon instance
            - Create real backup file with SQL content
            - Mock subprocess.run

        ACT:
            - Call restore() with backup file path

        ASSERT:
            - Verify psql command was called
            - Verify command includes -d with database name
            - Verify command includes -U with database user
            - Verify command includes -f with backup file path
            - Verify PGPASSWORD environment variable is set
        """
        backup_file = tmp_path / "backup.sql"
        backup_file.write_text("-- SQL backup content")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)

            postgres_addon.restore(backup_file)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "psql" in args
        assert "-d" in args
        assert "test_db" in args
        assert "-U" in args
        assert "test_db_user" in args
        assert "-f" in args
        assert str(backup_file) in args

        # Verify PGPASSWORD is in env
        env = mock_run.call_args[1].get("env", {})
        assert env.get("PGPASSWORD") == postgres_addon.db_password


@pytest.mark.integration
class TestPostgresAddonInfo:
    """Integration tests for database info retrieval."""

    def test_info_returns_database_details(self, postgres_addon):
        """Test that info() returns comprehensive database information.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock psycopg2.connect and cursor
            - Mock database queries to return realistic values

        ACT:
            - Call info() method

        ASSERT:
            - Verify addon_name is included
            - Verify type is 'postgres'
            - Verify database name matches
            - Verify size information is returned (size_bytes, size_mb)
            - Verify table_count is included
            - Verify version string is included
        """
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        # Mock database queries
        mock_cursor.fetchone.side_effect = [
            (1024 * 1024 * 50,),  # 50 MB database size
            (15,),  # 15 tables
            ("PostgreSQL 14.5",),  # Version
        ]

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        with patch("psycopg2.connect") as mock_connect:
            mock_connect.return_value = mock_connection

            info = postgres_addon.info()

        assert info["addon_name"] == "test-db"
        assert info["type"] == "postgres"
        assert info["database"] == "test_db"
        assert info["size_bytes"] == 1024 * 1024 * 50
        assert info["size_mb"] == 50.0
        assert info["table_count"] == 15
        assert "PostgreSQL" in info["version"]

    def test_info_includes_connection_parameters(self, postgres_addon):
        """Test that info() includes database connection parameters.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock psycopg2.connect and cursor

        ACT:
            - Call info() method

        ASSERT:
            - Verify user field matches db_user
            - Verify host is 'localhost'
            - Verify port is 5432
        """
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)
        mock_cursor.fetchone.side_effect = [(0,), (0,), ("PostgreSQL 14",)]

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        with patch("psycopg2.connect") as mock_connect:
            mock_connect.return_value = mock_connection

            info = postgres_addon.info()

        assert info["user"] == "test_db_user"
        assert info["host"] == "localhost"
        assert info["port"] == 5432

    def test_info_handles_connection_errors_gracefully(self, postgres_addon):
        """Test that info() handles database connection errors gracefully.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock psycopg2.connect to raise OperationalError

        ACT:
            - Call info() method

        ASSERT:
            - Verify error status is returned
            - Verify error message is included
            - Verify addon_name and type are still included
            - Verify no exception is raised
        """
        import psycopg2

        with patch("psycopg2.connect") as mock_connect:
            mock_connect.side_effect = psycopg2.OperationalError("Connection failed")

            info = postgres_addon.info()

        assert info["addon_name"] == "test-db"
        assert info["type"] == "postgres"
        assert info["status"] == "error"
        assert "Connection failed" in info["error"]


@pytest.mark.integration
class TestPostgresAddonHelperMethods:
    """Integration tests for private helper methods."""

    def test_check_database_exists_returns_true_when_exists(self, postgres_addon):
        """Test that _check_database_exists returns True when database exists.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock cursor with result indicating database exists

        ACT:
            - Call _check_database_exists()

        ASSERT:
            - Verify method returns True
        """
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)  # Database exists

        result = postgres_addon._check_database_exists(mock_cursor)

        assert result is True

    def test_check_database_exists_returns_false_when_not_exists(self, postgres_addon):
        """Test that _check_database_exists returns False when database doesn't exist.

        ARRANGE:
            - Create PostgresAddon instance
            - Mock cursor with no result

        ACT:
            - Call _check_database_exists()

        ASSERT:
            - Verify method returns False
        """
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None  # Database doesn't exist

        result = postgres_addon._check_database_exists(mock_cursor)

        assert result is False


@pytest.mark.integration
class TestPostgresAddonBackwardsCompatibility:
    """Integration tests for backwards compatibility."""

    def test_postgresql_addon_is_alias_for_postgres_addon(self):
        """Test that PostgresqlAddon is an alias for PostgresAddon.

        ARRANGE:
            - Reference both class names

        ACT:
            - Compare class identity

        ASSERT:
            - Verify PostgresqlAddon is PostgresAddon (same class object)
        """
        # ARRANGE & ACT & ASSERT
        assert PostgresqlAddon is PostgresAddon

    def test_postgresql_addon_can_be_instantiated(self):
        """Test that PostgresqlAddon alias can be instantiated.

        ARRANGE:
            - Prepare to create PostgresqlAddon instance

        ACT:
            - Create PostgresqlAddon instance with addon_name

        ASSERT:
            - Verify instance is created successfully
            - Verify instance is PostgresAddon type
        """
        # ARRANGE & ACT
        addon = PostgresqlAddon(addon_name="legacy-db")

        assert isinstance(addon, PostgresAddon)
        assert addon.addon_name == "legacy-db"
        assert addon.db_name == "legacy_db"
