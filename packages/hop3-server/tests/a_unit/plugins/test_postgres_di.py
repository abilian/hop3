# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for PostgreSQL DI integration."""

from __future__ import annotations

import os
from unittest.mock import Mock

from dishka import Provider, Scope, make_container, provide

from hop3.di import create_container
from hop3.lib.config import Config
from hop3.plugins.postgresql.admin import PostgresAdmin


def test_postgres_admin_from_config():
    """Test creating PostgresAdmin from Config."""
    config = Config(env_prefix="POSTGRES_")
    admin = PostgresAdmin.from_config(config)

    # Should use default values when env vars not set
    assert admin.host == "localhost"
    assert admin.port == 5432
    assert admin.superuser == "postgres"


def test_postgres_admin_get_connection_params():
    """Test PostgresAdmin connection parameters."""
    admin = PostgresAdmin(
        host="testhost",
        port=5433,
        superuser="testuser",
        superuser_password="testpass",
    )

    params = admin.get_connection_params()

    assert params["host"] == "testhost"
    assert params["port"] == 5433
    assert params["user"] == "testuser"
    assert params["dbname"] == "template1"
    assert params["password"] == "testpass"


def test_postgres_admin_get_connection_params_no_password():
    """Test connection parameters without password."""
    admin = PostgresAdmin(
        host="testhost",
        port=5433,
        superuser="testuser",
    )

    params = admin.get_connection_params("mydb")

    assert params["dbname"] == "mydb"
    assert "password" not in params


def test_postgres_admin_get_dsn():
    """Test DSN generation."""
    admin = PostgresAdmin(
        host="testhost",
        port=5433,
        superuser="testuser",
        superuser_password="testpass",
    )

    # Without password
    dsn = admin.get_dsn("mydb", include_password=False)
    assert dsn == "postgresql://testuser@testhost:5433/mydb"

    # With password
    dsn_with_pass = admin.get_dsn("mydb", include_password=True)
    assert dsn_with_pass == "postgresql://testuser:testpass@testhost:5433/mydb"


def test_postgres_admin_provided_by_plugin():
    """Test that PostgreSQL plugin provides PostgresAdmin service."""
    # Use create_container() to get full plugin integration
    container = create_container()
    try:
        admin = container.get(PostgresAdmin)

        assert admin is not None
        assert isinstance(admin, PostgresAdmin)
        # Should use default config values
        assert admin.host == "localhost"
        assert admin.port == 5432
    finally:
        container.close()


def test_postgres_admin_is_singleton():
    """Test that PostgresAdmin is a singleton in APP scope."""
    container = create_container()
    try:
        admin1 = container.get(PostgresAdmin)
        admin2 = container.get(PostgresAdmin)

        # Same instance due to APP scope
        assert admin1 is admin2
    finally:
        container.close()


def test_postgres_admin_with_custom_config():
    """Test PostgresAdmin with custom configuration."""
    # Set custom config via environment
    os.environ["POSTGRES_HOST"] = "customhost"
    os.environ["POSTGRES_PORT"] = "5433"
    os.environ["POSTGRES_SUPERUSER"] = "customuser"

    try:
        admin = PostgresAdmin.from_config()

        assert admin.host == "customhost"
        assert admin.port == 5433
        assert admin.superuser == "customuser"
    finally:
        # Clean up
        os.environ.pop("POSTGRES_HOST", None)
        os.environ.pop("POSTGRES_PORT", None)
        os.environ.pop("POSTGRES_SUPERUSER", None)


def test_postgres_admin_with_mock_provider():
    """Test PostgresAdmin with mocked provider for testing."""

    class MockPostgresProvider(Provider):
        """Mock provider for testing."""

        scope = Scope.APP

        @provide
        def get_postgres_admin(self) -> PostgresAdmin:
            mock = Mock(spec=PostgresAdmin)
            mock.host = "mockhost"
            mock.port = 9999
            mock.get_connection_params.return_value = {"host": "mockhost"}
            return mock

    container = make_container(MockPostgresProvider())
    try:
        admin = container.get(PostgresAdmin)

        assert admin.host == "mockhost"
        assert admin.port == 9999

        params = admin.get_connection_params()
        assert params == {"host": "mockhost"}
        admin.get_connection_params.assert_called_once()
    finally:
        container.close()
