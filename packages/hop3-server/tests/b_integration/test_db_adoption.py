# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for adopting pre-Alembic databases on db:upgrade.

Incident (test-ci, 2026-06-04): `hop3-deploy` ran `db:upgrade` against a
server whose `hop3.db` was created by `metadata.create_all()` and never
stamped (orm/session.py's create_all fallback — the universal bootstrap
path). `upgrade` replayed from base and the first delta died with
"duplicate column name: error_message".

This is structural, not host-specific: every Hop3 DB is an unstamped,
create_all'd, schema-complete database. These tests pin that
`db:upgrade` now *adopts* such a DB (stamps it, applies only missing
deltas) instead of failing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from hop3.orm import get_session_factory, reset_session_factory_cache
from hop3.orm.app import App
from hop3.server.cli.db import DbUpgradeCmd

if TYPE_CHECKING:
    from pathlib import Path

HEAD_REVISION = "a3f1c9e2b4d6"
BASE_REVISION = "d20dd80dafca"


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch):
    """Point Alembic (via env.py) and the adopt check at a temp SQLite file."""
    uri = f"sqlite:///{tmp_path / 'adopt.db'}"
    monkeypatch.setenv("HOP3_DATABASE_URI", uri)
    reset_session_factory_cache()
    yield uri
    reset_session_factory_cache()


def _current_revision(uri: str) -> str | None:
    engine = create_engine(uri)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


def _app_columns(uri: str) -> set[str]:
    engine = create_engine(uri)
    try:
        return {c["name"] for c in inspect(engine).get_columns("app")}
    finally:
        engine.dispose()


def _create_all_unstamped(uri: str) -> None:
    """Reproduce the historical bootstrap: full schema, no alembic stamp."""
    engine = create_engine(uri)
    App.metadata.create_all(engine)
    engine.dispose()


# ---- the incident: unstamped create_all DB -------------------------------


def test_upgrade_adopts_unstamped_populated_db(temp_db: str) -> None:
    """The exact failure: a create_all'd, unstamped DB must upgrade cleanly."""
    _create_all_unstamped(temp_db)
    assert _current_revision(temp_db) is None  # unstamped, like hop3-dev

    DbUpgradeCmd().run()  # must NOT raise / SystemExit on duplicate column

    assert _current_revision(temp_db) == HEAD_REVISION
    cols = _app_columns(temp_db)
    assert "error_message" in cols
    assert "runtime" in cols


def test_upgrade_is_idempotent_on_adopted_db(temp_db: str) -> None:
    """Running db:upgrade twice is a no-op the second time."""
    _create_all_unstamped(temp_db)
    DbUpgradeCmd().run()
    DbUpgradeCmd().run()  # second run: already stamped head
    assert _current_revision(temp_db) == HEAD_REVISION


# ---- empty DB bootstrap --------------------------------------------------


def test_upgrade_bootstraps_empty_db(temp_db: str) -> None:
    """A truly empty DB (no tables) gets built + stamped, despite the empty
    initial migration."""
    assert _current_revision(temp_db) is None

    DbUpgradeCmd().run()

    engine = create_engine(temp_db)
    try:
        assert inspect(engine).has_table("app")
    finally:
        engine.dispose()
    assert _current_revision(temp_db) == HEAD_REVISION


# ---- behind-head adoption (gap fill via idempotent deltas) ---------------


def test_upgrade_fills_missing_column_on_behind_head_db(temp_db: str) -> None:
    """A create_all DB from an older version (has error_message but not
    runtime) must get the missing column when adopted — proving the
    idempotent deltas skip-present-but-add-missing.
    """
    _create_all_unstamped(temp_db)
    # Simulate "older create_all": drop runtime so the DB sits between
    # revisions (has error_message, lacks runtime), still unstamped.
    engine = create_engine(temp_db)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE app DROP COLUMN runtime")
    finally:
        engine.dispose()
    assert "runtime" not in _app_columns(temp_db)
    assert "error_message" in _app_columns(temp_db)

    DbUpgradeCmd().run()

    cols = _app_columns(temp_db)
    assert "runtime" in cols  # the genuinely-missing delta was applied
    assert "error_message" in cols  # the present delta was skipped, not dup'd
    assert _current_revision(temp_db) == HEAD_REVISION


# ---- session bootstrap: fresh DBs are born stamped -----------------------


def test_get_session_factory_stamps_fresh_file_db(temp_db: str) -> None:
    """A brand-new file database must come out with its schema AND stamped at
    head, so it's consistent for Alembic from birth (no later adoption needed).
    """
    get_session_factory(temp_db)

    engine = create_engine(temp_db)
    try:
        assert inspect(engine).has_table("app")
    finally:
        engine.dispose()
    assert _current_revision(temp_db) == HEAD_REVISION


def test_get_session_factory_leaves_existing_unstamped_db_alone(
    temp_db: str,
) -> None:
    """An EXISTING unstamped DB must not be auto-migrated/stamped on boot —
    that is db:upgrade's gated job. session.py only bootstraps fresh DBs.
    """
    _create_all_unstamped(temp_db)
    assert _current_revision(temp_db) is None

    get_session_factory(temp_db)

    # Still unstamped: the schema is intact but adoption is left to db:upgrade.
    assert _current_revision(temp_db) is None
    assert "error_message" in _app_columns(temp_db)
