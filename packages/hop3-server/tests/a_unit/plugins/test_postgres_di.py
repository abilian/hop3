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


# Tests for URL parsing


def test_postgres_admin_from_url():
    """Test creating PostgresAdmin from a PostgreSQL URL."""
    url = "postgresql://myuser:mypassword@db.example.com:5433/mydb"
    admin = PostgresAdmin.from_url(url)

    assert admin.host == "db.example.com"
    assert admin.port == 5433
    assert admin.superuser == "myuser"
    assert admin.superuser_password == "mypassword"


def test_postgres_admin_from_url_default_port():
    """Test URL parsing with default port."""
    url = "postgresql://admin:secret@localhost/postgres"
    admin = PostgresAdmin.from_url(url)

    assert admin.host == "localhost"
    assert admin.port == 5432  # Default
    assert admin.superuser == "admin"
    assert admin.superuser_password == "secret"


def test_postgres_admin_from_url_no_password():
    """Test URL parsing without password (peer auth)."""
    url = "postgresql://postgres@localhost/postgres"
    admin = PostgresAdmin.from_url(url)

    assert admin.host == "localhost"
    assert admin.superuser == "postgres"
    assert admin.superuser_password is None


def test_postgres_admin_from_url_postgres_scheme():
    """Test URL parsing with 'postgres' scheme (alternative spelling)."""
    url = "postgres://user:pass@host:5432/db"
    admin = PostgresAdmin.from_url(url)

    assert admin.host == "host"
    assert admin.superuser == "user"


def test_postgres_admin_from_url_invalid_scheme():
    """Test URL parsing rejects invalid scheme."""
    with pytest.raises(ValueError, match="Invalid PostgreSQL URL scheme"):
        PostgresAdmin.from_url("mysql://user:pass@host/db")


def test_postgres_admin_from_url_missing_host():
    """Test URL parsing requires hostname."""
    with pytest.raises(ValueError, match="must include a hostname"):
        PostgresAdmin.from_url("postgresql:///mydb")


def test_postgres_admin_from_url_missing_user():
    """Test URL parsing requires username."""
    with pytest.raises(ValueError, match="must include a username"):
        PostgresAdmin.from_url("postgresql://localhost/mydb")
