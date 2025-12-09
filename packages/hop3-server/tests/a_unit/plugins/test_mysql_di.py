# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for MySQL DI integration."""

from __future__ import annotations

import pytest

from hop3.di import create_container
from hop3.lib.config import Config
from hop3.plugins.mysql.admin import MySQLAdmin


def test_mysql_admin_from_config():
    """Test creating MySQLAdmin from Config."""
    config = Config(env_prefix="MYSQL_")
    admin = MySQLAdmin.from_config(config)

    assert admin.host == "localhost"
    assert admin.port == 3306
    assert admin.superuser == "root"


def test_mysql_admin_get_connection_params():
    """Test MySQLAdmin connection parameters."""
    admin = MySQLAdmin(
        host="testhost",
        port=3307,
        superuser="testuser",
        superuser_password="testpass",
    )

    params = admin.get_connection_params()

    assert params["host"] == "testhost"
    assert params["port"] == 3307
    assert params["user"] == "testuser"
    assert params["password"] == "testpass"
    assert "database" not in params  # No database by default


def test_mysql_admin_get_connection_params_with_database():
    """Test connection parameters with database specified."""
    admin = MySQLAdmin(
        host="testhost",
        port=3307,
        superuser="testuser",
        superuser_password="testpass",
    )

    params = admin.get_connection_params("mydb")

    assert params["database"] == "mydb"


def test_mysql_admin_get_connection_params_no_password():
    """Test connection parameters without password."""
    admin = MySQLAdmin(
        host="testhost",
        port=3307,
        superuser="testuser",
    )

    params = admin.get_connection_params("mydb")

    assert params["database"] == "mydb"
    assert "password" not in params


def test_mysql_admin_get_dsn():
    """Test DSN generation."""
    admin = MySQLAdmin(
        host="testhost",
        port=3307,
        superuser="testuser",
        superuser_password="testpass",
    )

    dsn = admin.get_dsn("mydb", include_password=False)
    assert dsn == "mysql://testuser@testhost:3307/mydb"

    dsn_with_pass = admin.get_dsn("mydb", include_password=True)
    assert dsn_with_pass == "mysql://testuser:testpass@testhost:3307/mydb"


def test_mysql_admin_get_dsn_no_database():
    """Test DSN generation without database."""
    admin = MySQLAdmin(
        host="testhost",
        port=3307,
        superuser="testuser",
    )

    dsn = admin.get_dsn()
    assert dsn == "mysql://testuser@testhost:3307"


@pytest.fixture
def container():
    """Create container with plugin providers."""
    container = create_container()
    yield container
    container.close()


def test_mysql_admin_provided_by_plugin(container):
    """Test that MySQL plugin provides MySQLAdmin service."""
    admin = container.get(MySQLAdmin)

    assert isinstance(admin, MySQLAdmin)
    assert admin.host == "localhost"
    assert admin.port == 3306


def test_mysql_admin_is_singleton(container):
    """Test that MySQLAdmin is a singleton in APP scope."""
    admin1 = container.get(MySQLAdmin)
    admin2 = container.get(MySQLAdmin)

    assert admin1 is admin2


# Tests for URL parsing


def test_mysql_admin_from_url():
    """Test creating MySQLAdmin from a MySQL URL."""
    url = "mysql://myuser:mypassword@db.example.com:3307/mydb"
    admin = MySQLAdmin.from_url(url)

    assert admin.host == "db.example.com"
    assert admin.port == 3307
    assert admin.superuser == "myuser"
    assert admin.superuser_password == "mypassword"


def test_mysql_admin_from_url_default_port():
    """Test URL parsing with default port."""
    url = "mysql://admin:secret@localhost/mydb"
    admin = MySQLAdmin.from_url(url)

    assert admin.host == "localhost"
    assert admin.port == 3306  # Default
    assert admin.superuser == "admin"
    assert admin.superuser_password == "secret"


def test_mysql_admin_from_url_no_password():
    """Test URL parsing without password."""
    url = "mysql://root@localhost/mysql"
    admin = MySQLAdmin.from_url(url)

    assert admin.host == "localhost"
    assert admin.superuser == "root"
    assert admin.superuser_password is None


def test_mysql_admin_from_url_pymysql_scheme():
    """Test URL parsing with 'mysql+pymysql' scheme."""
    url = "mysql+pymysql://user:pass@host:3306/db"
    admin = MySQLAdmin.from_url(url)

    assert admin.host == "host"
    assert admin.superuser == "user"


def test_mysql_admin_from_url_mysqlconnector_scheme():
    """Test URL parsing with 'mysql+mysqlconnector' scheme."""
    url = "mysql+mysqlconnector://user:pass@host:3306/db"
    admin = MySQLAdmin.from_url(url)

    assert admin.host == "host"
    assert admin.superuser == "user"


def test_mysql_admin_from_url_invalid_scheme():
    """Test URL parsing rejects invalid scheme."""
    with pytest.raises(ValueError, match="Invalid MySQL URL scheme"):
        MySQLAdmin.from_url("postgresql://user:pass@host/db")


def test_mysql_admin_from_url_missing_host():
    """Test URL parsing requires hostname."""
    with pytest.raises(ValueError, match="must include a hostname"):
        MySQLAdmin.from_url("mysql:///mydb")


def test_mysql_admin_from_url_missing_user():
    """Test URL parsing requires username."""
    with pytest.raises(ValueError, match="must include a username"):
        MySQLAdmin.from_url("mysql://localhost/mydb")
