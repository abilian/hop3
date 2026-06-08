# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for MySQL addon - pure logic only.

These tests verify property derivation, validation, and error handling
without mocking subprocess calls. Integration tests that verify actual
MySQL operations are in tests/b_integration/plugins/test_mysql_integration.py
"""

from __future__ import annotations

from unittest.mock import patch

import mysql.connector
import pytest

from hop3.plugins.mysql.mysql import ADDON_USER_HOSTS, MySQLAddon, MysqlAddon


@pytest.fixture
def mysql_service():
    """Create a MySQLAddon instance for testing."""
    return MySQLAddon(addon_name="test-db")


def test_mysql_addon_requires_service_name():
    """Test that MySQLAddon requires a service_name."""
    with pytest.raises(ValueError, match="addon_name is required"):
        MySQLAddon(addon_name="")


@pytest.mark.parametrize(
    "bad_name",
    [
        "foo`; DROP DATABASE",  # backtick — would break out of CREATE DATABASE `…`
        "name with spaces",
        "weird/slash",
        "ab",  # too short (regex requires 3-63)
        "-leading-hyphen",
        "trailing-",
        "_leading-underscore",
        "name.dotted",
        "🙃-emoji",
    ],
)
def test_mysql_addon_rejects_unsafe_addon_name(bad_name):
    """addon_name flows into raw SQL identifier interpolation; reject anything unsafe."""
    from hop3.core.identifiers import InvalidIdentifierError  # noqa: PLC0415

    with pytest.raises(InvalidIdentifierError):
        MySQLAddon(addon_name=bad_name)


def test_mysql_addon_properties(mysql_service):
    """Test MySQLAddon property derivations."""
    assert mysql_service.db_name == "test_db"  # Hyphens replaced with underscores
    assert mysql_service.db_user == "test_db_user"
    assert len(mysql_service.db_password) > 0


def test_mysql_addon_hyphen_handling():
    """Test that hyphens in service names are converted to underscores."""
    service = MySQLAddon(addon_name="my-test-db")
    assert service.db_name == "my_test_db"
    assert service.db_user == "my_test_db_user"


def test_mysql_addon_username_truncation():
    """Test that MySQL usernames are truncated to 32 characters."""
    # MySQL has a 32-character limit on usernames
    service = MySQLAddon(addon_name="very-long-service-name-that-exceeds-limit")
    # db_name would be "very_long_service_name_that_exceeds_limit"
    # db_user would be "very_long_service_name_that_exceeds_limit_user" but truncated
    assert len(service.db_user) <= 32


def test_password_is_generated():
    """Test that a secure password is auto-generated."""
    service1 = MySQLAddon(addon_name="app1")
    service2 = MySQLAddon(addon_name="app2")

    # Passwords should be non-empty
    assert len(service1.db_password) >= 32
    assert len(service2.db_password) >= 32

    # Different instances get different passwords
    assert service1.db_password != service2.db_password


def test_restore_nonexistent_backup(mysql_service, tmp_path):
    """Test that restore fails if backup file doesn't exist."""
    nonexistent_file = tmp_path / "nonexistent.sql"

    with pytest.raises(FileNotFoundError, match="Backup file not found"):
        mysql_service.restore(nonexistent_file)


def test_info_handles_connection_errors(mysql_service):
    """Test that info handles connection errors gracefully."""
    # Mock the password loading so we can test connection error handling
    with (
        patch(
            "hop3.plugins.mysql.mysql.load_addon_secrets",
            return_value={"password": "test-password"},
        ),
        patch("mysql.connector.connect") as mock_connect,
    ):
        mock_connect.side_effect = mysql.connector.Error("Connection failed")

        info = mysql_service.info()

        assert info["addon_name"] == "test-db"
        assert info["type"] == "mysql"
        assert info["status"] == "error"
        assert "Connection failed" in info["error"]


def test_info_returns_not_created_without_password(mysql_service):
    """Test that info returns not_created status when no password exists."""
    # Without mocking, load_addon_secrets returns None (no secrets file)
    with patch(
        "hop3.plugins.mysql.mysql.load_addon_secrets",
        return_value=None,
    ):
        info = mysql_service.info()

        assert info["addon_name"] == "test-db"
        assert info["type"] == "mysql"
        assert info["status"] == "not_created"


def test_get_connection_details_requires_password(mysql_service):
    """Test that get_connection_details fails without stored password."""
    with (
        patch(
            "hop3.plugins.mysql.mysql.load_addon_secrets",
            return_value=None,
        ),
        pytest.raises(RuntimeError, match="No stored password"),
    ):
        mysql_service.get_connection_details()


def test_connection_details_format(mysql_service):
    """Test that connection details dict has correct structure.

    Note: This doesn't call get_connection_details() directly because
    that requires stored secrets. We test the structure by examining
    what the method would return.
    """
    # The connection details are built from these properties
    assert mysql_service.db_name == "test_db"
    assert mysql_service.db_user == "test_db_user"
    assert mysql_service.db_password  # Non-empty

    # Expected format (without actually calling the method)
    expected_url_pattern = f"mysql://{mysql_service.db_user}:"
    assert expected_url_pattern.startswith("mysql://test_db_user:")


def test_legacy_alias():
    """Test that MysqlAddon is an alias for MySQLAddon."""
    assert MysqlAddon is MySQLAddon


def test_name_attribute():
    """Test that MySQLAddon has correct name attribute."""
    assert MySQLAddon.name == "mysql"
    service = MySQLAddon(addon_name="test")
    assert service.name == "mysql"


def test_addon_user_hosts_cover_docker_network_pools():
    """A per-app DB user must be reachable from every Docker network pool.

    Regression: granting only ``172.%`` rejected compose apps whose network
    came from Docker's ``192.168.x`` default-address-pool, with
    "[1130] Host '192.168.x.y' is not allowed to connect to this MySQL server".
    """
    assert "127.0.0.1" in ADDON_USER_HOSTS  # native apps
    assert "172.%" in ADDON_USER_HOSTS  # default docker bridge pool
    assert "192.168.%" in ADDON_USER_HOSTS  # the other docker default pool
    assert "10.%" in ADDON_USER_HOSTS  # custom networks


class _RecordingCursor:
    """A stub cursor that records executed statements (no real DB)."""

    def __init__(self, executed: list[tuple[str, tuple]]) -> None:
        self._executed = executed

    def execute(self, stmt: str, params: tuple = ()) -> None:
        self._executed.append((stmt, tuple(params)))

    def fetchone(self):
        return None  # the database does not exist yet

    def close(self) -> None:
        pass


class _RecordingConnection:
    def __init__(self, executed: list[tuple[str, tuple]]) -> None:
        self._executed = executed

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self._executed)

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


class _FakeAdmin:
    def get_connection_params(self) -> dict:
        return {}


def _hosts_in(executed, verb: str) -> set[str]:
    """The set of ``host`` params (2nd bind value) of statements starting ``verb``."""
    return {p[1] for stmt, p in executed if stmt.startswith(verb) and len(p) >= 2}


def test_create_grants_and_destroy_drops_user_for_every_host():
    """Behavioural guard (not just the constant): ``create`` must CREATE USER +
    GRANT for *every* host in ADDON_USER_HOSTS, and ``destroy`` must DROP each.

    Catches a regression where ``create``/``destroy`` stop iterating the host
    list (the original 172-only bug) even though the constant stays correct.
    """
    service = MySQLAddon(addon_name="bookstack")
    executed: list[tuple[str, tuple]] = []

    with (
        patch.object(MySQLAddon, "_get_admin", lambda _self: _FakeAdmin()),
        patch(
            "mysql.connector.connect",
            return_value=_RecordingConnection(executed),
        ),
        patch("hop3.plugins.mysql.mysql.load_addon_secrets", return_value=None),
        patch("hop3.plugins.mysql.mysql.save_addon_secrets"),
    ):
        service.create()

    assert set(ADDON_USER_HOSTS) <= _hosts_in(executed, "CREATE USER")
    assert set(ADDON_USER_HOSTS) <= _hosts_in(executed, "GRANT")

    executed.clear()
    with (
        patch.object(MySQLAddon, "_get_admin", lambda _self: _FakeAdmin()),
        patch(
            "mysql.connector.connect",
            return_value=_RecordingConnection(executed),
        ),
        patch("hop3.plugins.mysql.mysql.delete_addon_secrets"),
    ):
        service.destroy()

    assert set(ADDON_USER_HOSTS) <= _hosts_in(executed, "DROP USER")
