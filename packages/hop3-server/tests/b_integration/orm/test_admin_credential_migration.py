# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
The app_admin_credential migration's own create_table path (ADR 056).

Regression for a bug that reached a real box: the migration hardcoded a BIGINT
primary key, which on SQLite is NOT a rowid alias, so inserts with a NULL id
failed. Every other test uses ``create_all`` (where the migration's create is
guarded away), so this exercises the migration's create_table branch directly.
"""

from __future__ import annotations

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from hop3.alembic.versions import (
    b6c1d2e3f4a5_add_app_admin_credential as migration,
)


def test_migration_id_autoincrements_on_sqlite(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    with engine.begin() as conn:
        # FK target + a row to reference.
        conn.execute(text("CREATE TABLE app (id INTEGER NOT NULL PRIMARY KEY)"))
        conn.execute(text("INSERT INTO app (id) VALUES (1)"))

        # Run the migration's create_table branch (not create_all).
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration.upgrade()

        # The id must auto-assign (rowid) — a BIGINT PK on SQLite would not, and
        # this insert (NULL id) would fail with a NOT NULL constraint error.
        conn.execute(
            text(
                "INSERT INTO app_admin_credential "
                "(created_at, updated_at, app_id, encrypted_data, source, "
                "bootstrapped, surfaced) VALUES "
                "('2026-01-01', '2026-01-01', 1, 'x', 'generated', 0, 0)"
            )
        )
        row = conn.execute(text("SELECT id FROM app_admin_credential")).fetchone()
        assert row is not None
        assert row[0] is not None  # id was auto-assigned

    id_col = next(
        c
        for c in inspect(engine).get_columns("app_admin_credential")
        if c["name"] == "id"
    )
    assert "INT" in str(id_col["type"]).upper()
    engine.dispose()
