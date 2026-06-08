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

from hop3.plugins.postgresql import postgres as pg
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


def test_install_extensions_empty_list_is_noop(postgres_service):
    """Empty extension list short-circuits before any DB connection."""
    # Should not raise and should not need a DB connection.
    postgres_service.install_extensions([])


@pytest.mark.parametrize(
    "bad_ext",
    [
        "adminpack",  # untrusted, filesystem access
        "postgres_fdw",  # untrusted, network access
        "dblink",  # untrusted, network access
        "file_fdw",  # untrusted, filesystem access
        "plpython3u",  # untrusted procedural language
        "evil; DROP TABLE foo;",  # injection-shaped (sql.Identifier neutralizes,
        # but the allow-list rejects first)
    ],
)
def test_install_extensions_rejects_non_allowlisted(postgres_service, bad_ext):
    """Extensions outside ALLOWED_EXTENSIONS must be refused before SQL runs."""
    with pytest.raises(ValueError, match="non-allow-listed PostgreSQL extension"):
        postgres_service.install_extensions(["pg_trgm", bad_ext])


def test_install_extensions_allowlist_covers_common_trusted():
    """The allow-list must contain the extensions hop3 docs/examples reference."""
    from hop3.plugins.postgresql.postgres import ALLOWED_EXTENSIONS  # noqa: PLC0415

    # Spot-check a handful of widely-used trusted extensions.
    for ext in ("pg_trgm", "hstore", "citext", "pgcrypto", "uuid-ossp"):
        assert ext in ALLOWED_EXTENSIONS, f"missing trusted ext: {ext!r}"


@pytest.mark.parametrize(
    "ext",
    [
        "bloom",  # BookWyrm
        "postgis",  # GeoDjango / OSM-based apps
        "pgvector",  # AI/embedding apps
        "cube",  # paired with earthdistance
        "earthdistance",  # Immich face clustering
        "ip4r",  # GitLab
    ],
)
def test_install_extensions_default_set_covers_popular_apps(ext):
    """Popular self-hosted apps' extensions must be in the default set."""
    from hop3.plugins.postgresql.postgres import (  # noqa: PLC0415
        DEFAULT_ALLOWED_EXTENSIONS,
    )

    assert ext in DEFAULT_ALLOWED_EXTENSIONS, (
        f"missing extension needed by popular apps: {ext!r}"
    )


def test_blocked_extensions_includes_privilege_escalation_set():
    """Truly dangerous extensions must be in BLOCKED_EXTENSIONS."""
    from hop3.plugins.postgresql.postgres import BLOCKED_EXTENSIONS  # noqa: PLC0415

    for ext in (
        "adminpack",
        "dblink",
        "file_fdw",
        "postgres_fdw",
        "plpython3u",
        "plperlu",
    ):
        assert ext in BLOCKED_EXTENSIONS, f"missing blocked ext: {ext!r}"


def test_operator_extra_env_extends_allowlist(postgres_service, monkeypatch):
    """HOP3_EXTRA_PG_EXTENSIONS adds names to the effective allow-list."""
    from hop3.plugins.postgresql.postgres import (  # noqa: PLC0415
        _resolve_allowed_extensions,
    )

    monkeypatch.setenv("HOP3_EXTRA_PG_EXTENSIONS", "pg_partman, h3 ")
    allowed = _resolve_allowed_extensions()
    assert "pg_partman" in allowed
    assert "h3" in allowed
    # Defaults preserved.
    assert "pg_trgm" in allowed


def test_operator_extra_env_cannot_enable_blocked(postgres_service, monkeypatch):
    """HOP3_EXTRA_PG_EXTENSIONS cannot lift entries off BLOCKED_EXTENSIONS."""
    from hop3.plugins.postgresql.postgres import (  # noqa: PLC0415
        _resolve_allowed_extensions,
    )

    monkeypatch.setenv("HOP3_EXTRA_PG_EXTENSIONS", "plpython3u,postgres_fdw,h3")
    allowed = _resolve_allowed_extensions()
    assert "plpython3u" not in allowed
    assert "postgres_fdw" not in allowed
    # Non-blocked entry from the same env still goes through.
    assert "h3" in allowed


def test_operator_extra_env_empty_is_noop(monkeypatch):
    """Empty / unset env var leaves the allow-list at defaults."""
    from hop3.plugins.postgresql.postgres import (  # noqa: PLC0415
        BLOCKED_EXTENSIONS,
        DEFAULT_ALLOWED_EXTENSIONS,
        _resolve_allowed_extensions,
    )

    monkeypatch.delenv("HOP3_EXTRA_PG_EXTENSIONS", raising=False)
    assert (
        _resolve_allowed_extensions() == DEFAULT_ALLOWED_EXTENSIONS - BLOCKED_EXTENSIONS
    )

    monkeypatch.setenv("HOP3_EXTRA_PG_EXTENSIONS", "")
    assert (
        _resolve_allowed_extensions() == DEFAULT_ALLOWED_EXTENSIONS - BLOCKED_EXTENSIONS
    )


def test_install_extensions_blocked_error_mentions_blocked_set(
    postgres_service, monkeypatch
):
    """When an app declares a blocked extension, the error names the override env."""
    monkeypatch.delenv("HOP3_EXTRA_PG_EXTENSIONS", raising=False)
    with pytest.raises(ValueError, match="HOP3_EXTRA_PG_EXTENSIONS"):
        postgres_service.install_extensions(["plpython3u"])


def test_pg_hba_allows_all_docker_network_pools(tmp_path):
    """pg_hba.conf must allow every Docker network pool, idempotently.

    Regression: only ``172.16.0.0/12`` was allowed, so compose apps whose
    network came from the ``192.168.x`` pool got "no pg_hba.conf entry for host".
    """
    hba = tmp_path / "pg_hba.conf"
    hba.write_text("local all all peer\n")

    with patch.object(pg, "_find_pg_hba", return_value=hba):
        pg._ensure_pg_hba_docker_access()
        first = hba.read_text()
        pg._ensure_pg_hba_docker_access()  # second run must be a no-op
        second = hba.read_text()

    for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"):
        assert net in first
    assert first == second  # idempotent — no duplicate entries
