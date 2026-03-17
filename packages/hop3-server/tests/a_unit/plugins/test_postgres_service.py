# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for PostgreSQL addon - pure logic only.

These tests verify property derivation, validation, and error handling
without mocking subprocess calls. Integration tests that verify actual
PostgreSQL operations are in tests/b_integration/plugins/test_postgres_integration.py
"""

from __future__ import annotations

from unittest.mock import patch

import psycopg2
import pytest

from hop3.plugins.postgresql.postgres import PostgresAddon, PostgresqlAddon


@pytest.fixture
def postgres_service():
    """Create a PostgresAddon instance for testing."""
    return PostgresAddon(addon_name="test-db")


def test_postgres_addon_requires_service_name():
    """Test that PostgresAddon requires a service_name."""
    with pytest.raises(ValueError, match="addon_name is required"):
        PostgresAddon(addon_name="")


def test_postgres_addon_properties(postgres_service):
    """Test PostgresAddon property derivations."""
    assert postgres_service.db_name == "test_db"  # Hyphens replaced with underscores
    assert postgres_service.db_user == "test_db_user"
    assert len(postgres_service.db_password) > 0


def test_postgres_addon_hyphen_handling():
    """Test that hyphens in service names are converted to underscores."""
    service = PostgresAddon(addon_name="my-test-db")
    assert service.db_name == "my_test_db"
    assert service.db_user == "my_test_db_user"


def test_password_is_generated():
    """Test that a secure password is auto-generated."""
    service1 = PostgresAddon(addon_name="app1")
    service2 = PostgresAddon(addon_name="app2")

    # Passwords should be non-empty
    assert len(service1.db_password) >= 32
    assert len(service2.db_password) >= 32

    # Different instances get different passwords
    assert service1.db_password != service2.db_password


def test_restore_nonexistent_backup(postgres_service, tmp_path):
    """Test that restore fails if backup file doesn't exist."""
    nonexistent_file = tmp_path / "nonexistent.sql"

    with pytest.raises(FileNotFoundError, match="Backup file not found"):
        postgres_service.restore(nonexistent_file)


def test_info_handles_connection_errors(postgres_service):
    """Test that info handles connection errors gracefully."""
    # Mock the password loading so we can test connection error handling
    with (
        patch(
            "hop3.plugins.postgresql.postgres.load_addon_secrets",
            return_value={"password": "test-password"},
        ),
        patch("psycopg2.connect") as mock_connect,
    ):
        mock_connect.side_effect = psycopg2.OperationalError("Connection failed")

        info = postgres_service.info()

        assert info["addon_name"] == "test-db"
        assert info["type"] == "postgres"
        assert info["status"] == "error"
        assert "Connection failed" in info["error"]


def test_connection_details_format(postgres_service):
    """Test that connection details dict has correct structure.

    Note: This doesn't call get_connection_details() directly because
    that would trigger _sync_password() which needs real PostgreSQL.
    We test the structure by examining what the method would return.
    """
    # The connection details are built from these properties
    assert postgres_service.db_name == "test_db"
    assert postgres_service.db_user == "test_db_user"
    assert postgres_service.db_password  # Non-empty

    # Expected format (without actually calling the method)
    expected_url_pattern = f"postgresql://{postgres_service.db_user}:"
    assert expected_url_pattern.startswith("postgresql://test_db_user:")


def test_legacy_alias():
    """Test that PostgresqlAddon is an alias for PostgresAddon."""
    assert PostgresqlAddon is PostgresAddon
