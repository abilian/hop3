# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for PostgreSQL service strategy."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import psycopg2
import pytest

from hop3.plugins.postgresql.postgres import PostgresqlService, PostgresService


@pytest.fixture
def postgres_service():
    """Create a PostgresService instance for testing."""
    return PostgresService(service_name="test-db")


def test_postgres_service_requires_service_name():
    """Test that PostgresService requires a service_name."""
    with pytest.raises(ValueError, match="service_name is required"):
        PostgresService(service_name="")


def test_postgres_service_properties(postgres_service):
    """Test PostgresService property derivations."""
    assert postgres_service.db_name == "test_db"  # Hyphens replaced with underscores
    assert postgres_service.db_user == "test_db_user"
    assert len(postgres_service.db_password) > 0


def test_postgres_service_hyphen_handling():
    """Test that hyphens in service names are converted to underscores."""
    service = PostgresService(service_name="my-test-db")
    assert service.db_name == "my_test_db"
    assert service.db_user == "my_test_db_user"


def test_get_connection_details(postgres_service):
    """Test that connection details are properly formatted."""
    details = postgres_service.get_connection_details()

    assert "DATABASE_URL" in details
    assert details["DATABASE_URL"].startswith("postgresql://")
    assert "test_db" in details["DATABASE_URL"]
    assert details["PGDATABASE"] == "test_db"
    assert details["PGUSER"] == "test_db_user"
    assert details["PGHOST"] == "localhost"
    assert details["PGPORT"] == "5432"
    assert "PGPASSWORD" in details


def test_create_database_success(postgres_service):
    """Test successful database creation."""
    mock_connection = MagicMock()
    mock_cursor = MagicMock()

    with patch("psycopg2.connect") as mock_connect:
        mock_connect.return_value = mock_connection
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        # Database doesn't exist
        mock_cursor.fetchone.return_value = None

        postgres_service.create()

        # Verify database check was called
        assert mock_cursor.execute.call_count >= 1
        # Verify database creation was attempted
        mock_connection.set_isolation_level.assert_called_once()


def test_create_database_already_exists(postgres_service):
    """Test that create is idempotent when database already exists."""
    mock_connection = MagicMock()
    mock_cursor = MagicMock()

    with patch("psycopg2.connect") as mock_connect:
        mock_connect.return_value = mock_connection
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        # Database already exists
        mock_cursor.fetchone.return_value = (1,)

        postgres_service.create()

        # Should check for existence but not create
        assert mock_cursor.execute.call_count == 1  # Only the check query


def test_destroy_database(postgres_service):
    """Test database destruction."""
    mock_connection = MagicMock()
    mock_cursor = MagicMock()

    with patch("psycopg2.connect") as mock_connect:
        mock_connect.return_value = mock_connection
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        postgres_service.destroy()

        # Verify DROP commands were executed
        assert mock_cursor.execute.call_count == 2  # DROP DATABASE and DROP USER
        calls = [str(call) for call in mock_cursor.execute.call_args_list]
        assert any("DROP DATABASE" in str(call) for call in calls)
        assert any("DROP USER" in str(call) for call in calls)


def test_backup_creates_file(postgres_service, tmp_path):
    """Test that backup creates a file."""
    with (
        patch("subprocess.run") as mock_run,
        patch("pathlib.Path.mkdir"),
        patch(
            "hop3.plugins.postgresql.postgres.Path",
            return_value=tmp_path / "backups" / "postgres",
        ),
    ):
        mock_run.return_value = Mock(returncode=0)

        _backup_path = postgres_service.backup()

        # Verify pg_dump was called
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "pg_dump" in args
        assert "-d" in args
        assert "test_db" in args


def test_restore_from_backup(postgres_service, tmp_path):
    """Test restoring from a backup file."""
    backup_file = tmp_path / "backup.sql"
    backup_file.write_text("-- SQL backup content")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0)

        postgres_service.restore(backup_file)

        # Verify psql was called
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "psql" in args
        assert "-d" in args
        assert "test_db" in args


def test_restore_nonexistent_backup(postgres_service, tmp_path):
    """Test that restore fails if backup file doesn't exist."""
    nonexistent_file = tmp_path / "nonexistent.sql"

    with pytest.raises(FileNotFoundError, match="Backup file not found"):
        postgres_service.restore(nonexistent_file)


def test_info_returns_database_details(postgres_service):
    """Test that info returns database information."""
    mock_connection = MagicMock()
    mock_cursor = MagicMock()

    with patch("psycopg2.connect") as mock_connect:
        mock_connect.return_value = mock_connection
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock database queries
        mock_cursor.fetchone.side_effect = [
            (1024 * 1024 * 50,),  # 50 MB database size
            (15,),  # 15 tables
            ("PostgreSQL 14.5",),  # Version
        ]

        info = postgres_service.info()

        assert info["service_name"] == "test-db"
        assert info["type"] == "postgres"
        assert info["database"] == "test_db"
        assert info["size_bytes"] == 1024 * 1024 * 50
        assert info["size_mb"] == 50.0
        assert info["table_count"] == 15
        assert "PostgreSQL" in info["version"]


def test_info_handles_connection_errors(postgres_service):
    """Test that info handles connection errors gracefully."""

    with patch("psycopg2.connect") as mock_connect:
        mock_connect.side_effect = psycopg2.OperationalError("Connection failed")

        info = postgres_service.info()

        assert info["service_name"] == "test-db"
        assert info["type"] == "postgres"
        assert info["status"] == "error"
        assert "Connection failed" in info["error"]


def test_check_database_exists(postgres_service):
    """Test database existence check."""
    mock_cursor = Mock()
    mock_cursor.fetchone.return_value = (1,)

    assert postgres_service._check_database_exists(mock_cursor) is True

    mock_cursor.fetchone.return_value = None
    assert postgres_service._check_database_exists(mock_cursor) is False


def test_create_database_executes_sql(postgres_service):
    """Test that _create_database executes proper SQL."""
    mock_cursor = Mock()

    postgres_service._create_database(mock_cursor)

    # Should execute two statements: CREATE USER and CREATE DATABASE
    assert mock_cursor.execute.call_count == 2

    calls = [str(call) for call in mock_cursor.execute.call_args_list]
    assert any("CREATE USER" in str(call) for call in calls)
    assert any("CREATE DATABASE" in str(call) for call in calls)


def test_legacy_alias():
    """Test that PostgresqlService is an alias for PostgresService."""

    assert PostgresqlService is PostgresService
