# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for PostgreSQL addon.

These tests run against a real PostgreSQL instance and verify actual
database operations (create, destroy, backup, restore, info).

Requirements:
- PostgreSQL must be installed and running
- Admin credentials must be configured via:
  - POSTGRES_ADMIN_URL=postgresql://user:pass@host:port/db, or
  - POSTGRES_HOST, POSTGRES_PORT, POSTGRES_SUPERUSER, POSTGRES_SUPERUSER_PASSWORD
- These tests are skipped if PostgreSQL is not available

Run with: pytest tests/b_integration/plugins/test_postgres_integration.py -v
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import uuid
from contextlib import suppress

import psycopg2
import psycopg2.extensions
import pytest

import hop3.plugins.postgresql.postgres as pg_module
from hop3.plugins.addons import generic_cli
from hop3.plugins.postgresql import cli as pg_cli
from hop3.plugins.postgresql.admin import PostgresAdmin
from hop3.plugins.postgresql.postgres import PostgresAddon


def postgres_available() -> bool:
    """
    Check if PostgreSQL is available for testing.

    Tries to connect using configured admin credentials.
    """
    try:
        admin = PostgresAdmin.from_config()
        conn = psycopg2.connect(**admin.get_connection_params())
        conn.close()
        return True
    except (psycopg2.OperationalError, psycopg2.Error):
        return False


# Skip all tests in this module if PostgreSQL is not available
pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (check POSTGRES_ADMIN_URL or POSTGRES_* config)",
)


@pytest.fixture
def admin():
    """Get PostgreSQL admin connection."""
    return PostgresAdmin.from_config()


@pytest.fixture
def unique_addon_name():
    """Generate a unique addon name for test isolation."""
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def postgres_addon(unique_addon_name):
    """Create a PostgresAddon and clean up after test."""
    addon = PostgresAddon(addon_name=unique_addon_name)
    yield addon
    # Cleanup: try to destroy even if test failed
    # Already destroyed or never created
    with suppress(RuntimeError, psycopg2.Error):
        addon.destroy()


def _database_exists(admin: PostgresAdmin, db_name: str) -> bool:
    """Check if a database exists using admin connection."""
    conn = psycopg2.connect(**admin.get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (db_name,),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def _user_exists(admin: PostgresAdmin, username: str) -> bool:
    """Check if a user/role exists using admin connection."""
    conn = psycopg2.connect(**admin.get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s",
                (username,),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


class TestPostgresCreate:
    """Tests for database creation."""

    def test_create_database(self, postgres_addon, admin):
        """Test that create() actually creates a PostgreSQL database."""
        postgres_addon.create()

        # Verify database exists
        assert _database_exists(admin, postgres_addon.db_name), (
            "Database was not created"
        )

        # Verify user exists
        assert _user_exists(admin, postgres_addon.db_user), "User was not created"

    def test_create_is_idempotent(self, postgres_addon, admin):
        """Test that calling create() twice doesn't fail."""
        postgres_addon.create()
        postgres_addon.create()  # Should not raise

        # Database should still exist
        assert _database_exists(admin, postgres_addon.db_name)

    def test_per_app_user_can_install_trusted_extension(self, postgres_addon, admin):
        """
        Per-app user should be able to CREATE EXTENSION for trusted extensions.

        On PG 15+, `public` schema CREATE is revoked from PUBLIC by default;
        owning the database is insufficient. The addon grants CREATE+USAGE on
        the public schema inside the new database so Django/Rails migrations
        that install `pg_trgm`, `bloom`, `hstore`, etc. succeed. Regression
        guard for the BookWyrm / Funkwhale / Mastodon-on-fresh-install class
        of failures.
        """
        postgres_addon.create()

        # Connect as the per-app user (not admin) to the per-app database.
        details = postgres_addon.get_connection_details()
        conn = psycopg2.connect(
            host=details["PGHOST"],
            port=int(details["PGPORT"]),
            dbname=details["PGDATABASE"],
            user=details["PGUSER"],
            password=details["PGPASSWORD"],
        )
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        try:
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
                assert cursor.fetchone() is not None, (
                    "pg_trgm extension was not installed"
                )
        finally:
            conn.close()


class TestPostgresDestroy:
    """Tests for database destruction."""

    def test_destroy_database(self, postgres_addon, admin):
        """Test that destroy() removes the database and user."""
        postgres_addon.create()
        postgres_addon.destroy()

        # Verify database is gone
        assert not _database_exists(admin, postgres_addon.db_name), (
            "Database was not destroyed"
        )

        # Verify user is gone
        assert not _user_exists(admin, postgres_addon.db_user), "User was not destroyed"


class TestPostgresConnectionDetails:
    """Tests for connection details."""

    def test_get_connection_details(self, postgres_addon):
        """Test that connection details allow actual database connection."""
        postgres_addon.create()
        details = postgres_addon.get_connection_details()

        # Verify all expected keys
        assert "DATABASE_URL" in details
        assert "PGDATABASE" in details
        assert "PGUSER" in details
        assert "PGPASSWORD" in details
        assert "PGHOST" in details
        assert "PGPORT" in details

        # Verify we can connect with these credentials
        conn = psycopg2.connect(
            host=details["PGHOST"],
            port=int(details["PGPORT"]),
            user=details["PGUSER"],
            password=details["PGPASSWORD"],
            dbname=details["PGDATABASE"],
        )
        conn.close()


class TestPostgresInfo:
    """Tests for database info."""

    def test_info_returns_details(self, postgres_addon):
        """Test that info() returns actual database information."""
        postgres_addon.create()
        info = postgres_addon.info()

        assert info["addon_name"] == postgres_addon.addon_name
        assert info["type"] == "postgres"
        assert info["database"] == postgres_addon.db_name
        assert "size_bytes" in info
        assert "table_count" in info
        assert "version" in info
        assert "PostgreSQL" in info["version"]


@pytest.mark.skipif(
    shutil.which("pg_dump") is None,
    reason="pg_dump not found in PATH (PostgreSQL client tools required)",
)
class TestPostgresBackupRestore:
    """Tests for backup and restore."""

    def test_backup_creates_file(self, postgres_addon, tmp_path):
        """Test that backup creates an actual SQL file."""
        # Temporarily override HOP3_ROOT for test
        original_root = pg_module.HOP3_ROOT
        pg_module.HOP3_ROOT = tmp_path

        try:
            postgres_addon.create()

            # Create a table with some data
            details = postgres_addon.get_connection_details()
            conn = psycopg2.connect(
                host=details["PGHOST"],
                port=int(details["PGPORT"]),
                user=details["PGUSER"],
                password=details["PGPASSWORD"],
                dbname=details["PGDATABASE"],
            )
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE test_data (id SERIAL, value TEXT)")
                cur.execute("INSERT INTO test_data (value) VALUES ('hello')")
            conn.commit()
            conn.close()

            # Create backup
            backup_path = postgres_addon.backup()

            # Verify backup file exists and contains SQL
            assert backup_path.exists()
            content = backup_path.read_text()
            assert "CREATE TABLE" in content or "test_data" in content

        finally:
            pg_module.HOP3_ROOT = original_root

    def test_restore_recovers_data(self, postgres_addon, tmp_path):
        """Test that restore actually recovers data."""
        original_root = pg_module.HOP3_ROOT
        pg_module.HOP3_ROOT = tmp_path

        try:
            postgres_addon.create()

            # Create data
            details = postgres_addon.get_connection_details()
            conn = psycopg2.connect(
                host=details["PGHOST"],
                port=int(details["PGPORT"]),
                user=details["PGUSER"],
                password=details["PGPASSWORD"],
                dbname=details["PGDATABASE"],
            )
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE test_data (id SERIAL, value TEXT)")
                cur.execute("INSERT INTO test_data (value) VALUES ('original')")
            conn.commit()
            conn.close()

            # Backup
            backup_path = postgres_addon.backup()

            # Drop the table (simulate data loss)
            conn = psycopg2.connect(
                host=details["PGHOST"],
                port=int(details["PGPORT"]),
                user=details["PGUSER"],
                password=details["PGPASSWORD"],
                dbname=details["PGDATABASE"],
            )
            with conn.cursor() as cur:
                cur.execute("DROP TABLE test_data")
            conn.commit()
            conn.close()

            # Restore
            postgres_addon.restore(backup_path)

            # Verify data is back
            conn = psycopg2.connect(
                host=details["PGHOST"],
                port=int(details["PGPORT"]),
                user=details["PGUSER"],
                password=details["PGPASSWORD"],
                dbname=details["PGDATABASE"],
            )
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM test_data")
                result = cur.fetchone()
            conn.close()

            assert result[0] == "original"

        finally:
            pg_module.HOP3_ROOT = original_root


def _app_sql(addon: PostgresAddon, *statements: str) -> list:
    """Run ``statements`` as the app's user; the last one's rows."""
    details = addon.get_connection_details()
    conn = psycopg2.connect(
        host=details["PGHOST"],
        port=int(details["PGPORT"]),
        user=details["PGUSER"],
        password=details["PGPASSWORD"],
        dbname=details["PGDATABASE"],
    )
    try:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
            rows = cur.fetchall() if cur.description else []
        conn.commit()
    finally:
        conn.close()
    return rows


def test_a_restore_over_the_live_database_gives_back_the_dump(
    postgres_addon, tmp_path, monkeypatch
):
    """
    LimeSurvey's rollback replayed its dump over the upgraded database: every
    CREATE failed on an existing table, psql exited 0, and both mixed.
    """
    monkeypatch.setattr(pg_module, "HOP3_ROOT", tmp_path)
    postgres_addon.create()
    _app_sql(
        postgres_addon,
        "CREATE TABLE answers (value TEXT)",
        "INSERT INTO answers VALUES ('before')",
    )
    backup_path = postgres_addon.backup()
    _app_sql(
        postgres_addon,
        "INSERT INTO answers VALUES ('after')",
        "CREATE TABLE added_by_the_upgrade (id INT)",
    )

    postgres_addon.restore(backup_path)

    assert _app_sql(postgres_addon, "SELECT value FROM answers") == [("before",)]
    tables = _app_sql(
        postgres_addon,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
    )
    assert tables == [("answers",)]
    # The app's user still owns what it created, and can write.
    _app_sql(postgres_addon, "INSERT INTO answers VALUES ('later')")


def test_a_dump_that_fails_leaves_the_live_database_alone(
    postgres_addon, tmp_path, monkeypatch
):
    monkeypatch.setattr(pg_module, "HOP3_ROOT", tmp_path)
    postgres_addon.create()
    _app_sql(
        postgres_addon,
        "CREATE TABLE answers (value TEXT)",
        "INSERT INTO answers VALUES ('live')",
    )
    broken = tmp_path / "backups" / "postgres" / "broken.sql"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("CREATE TABLE answers (value TEXT);\nNOT SQL;\n")

    with pytest.raises(subprocess.CalledProcessError):
        postgres_addon.restore(broken)

    assert _app_sql(postgres_addon, "SELECT value FROM answers") == [("live",)]


# A `pg_dump --no-owner` dump, as one taken on another platform usually is.
_DUMP_WITHOUT_OWNERS = b"""
CREATE TYPE public.mood AS ENUM ('ok', 'bad');
CREATE TABLE public.answers (id SERIAL PRIMARY KEY, value TEXT, mood public.mood);
INSERT INTO public.answers (value, mood) VALUES ('imported', 'ok');
CREATE VIEW public.ok_answers AS SELECT value FROM public.answers WHERE mood = 'ok';
CREATE FUNCTION public.answer_count() RETURNS bigint
    LANGUAGE sql AS 'SELECT count(*) FROM public.answers';
"""


def test_import_loads_a_dump_streamed_from_the_client(
    postgres_addon, tmp_path, monkeypatch
):
    """
    `addon postgres import` staged the upload in /tmp, which `restore` refuses:
    the command could never succeed, and a stubbed `restore` hid it.
    """
    monkeypatch.setattr(pg_module, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(generic_cli, "HOP3_ROOT", tmp_path)
    postgres_addon.create()

    pg_cli.AddonPostgresImportCmd().call(
        postgres_addon.addon_name,
        import_data=base64.b64encode(_DUMP_WITHOUT_OWNERS).decode(),
    )

    assert _app_sql(postgres_addon, "SELECT value FROM ok_answers") == [("imported",)]
    assert list((tmp_path / "backups" / "postgres").iterdir()) == []


def test_a_dump_without_owners_is_given_to_the_app_user(
    postgres_addon, tmp_path, monkeypatch
):
    """
    Loaded as the admin, a dump without `OWNER TO` left every object the
    admin's: the restore succeeded and the app got "permission denied".
    """
    monkeypatch.setattr(pg_module, "HOP3_ROOT", tmp_path)
    postgres_addon.create()
    dump = tmp_path / "backups" / "postgres" / "foreign.sql"
    dump.parent.mkdir(parents=True)
    dump.write_bytes(_DUMP_WITHOUT_OWNERS)

    postgres_addon.restore(dump)

    # Everything the app does to its own data: write (and the serial's
    # sequence with it), read a view, call a function, change the schema.
    _app_sql(
        postgres_addon,
        "INSERT INTO answers (value, mood) VALUES ('later', 'bad')",
        "ALTER TABLE answers ADD COLUMN note TEXT",
        "ALTER TYPE mood ADD VALUE 'meh'",
        "CREATE OR REPLACE VIEW ok_answers AS SELECT value, note FROM answers",
    )
    assert _app_sql(postgres_addon, "SELECT answer_count()") == [(2,)]
