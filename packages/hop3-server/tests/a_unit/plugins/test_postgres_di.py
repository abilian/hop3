# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for PostgreSQL DI integration."""

from __future__ import annotations

import pytest

from hop3.di import create_container
from hop3.lib.config import Config
from hop3.plugins.postgresql.admin import PostgresAdmin


def test_postgres_admin_from_config():
    """Test creating PostgresAdmin from Config."""
    config = Config(env_prefix="POSTGRES_")
    admin = PostgresAdmin.from_config(config)

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

    dsn = admin.get_dsn("mydb", include_password=False)
    assert dsn == "postgresql://testuser@testhost:5433/mydb"

    dsn_with_pass = admin.get_dsn("mydb", include_password=True)
    assert dsn_with_pass == "postgresql://testuser:testpass@testhost:5433/mydb"


@pytest.fixture
def container():
    """Create container with plugin providers."""
    container = create_container()
    yield container
    container.close()


def test_postgres_admin_provided_by_plugin(container):
    """Test that PostgreSQL plugin provides PostgresAdmin service."""
    admin = container.get(PostgresAdmin)

    assert isinstance(admin, PostgresAdmin)
    assert admin.host == "localhost"
    assert admin.port == 5432


def test_postgres_admin_is_singleton(container):
    """Test that PostgresAdmin is a singleton in APP scope."""
    admin1 = container.get(PostgresAdmin)
    admin2 = container.get(PostgresAdmin)

    assert admin1 is admin2
