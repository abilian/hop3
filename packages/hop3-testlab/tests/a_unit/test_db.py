# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The result-store engine is dialect-aware: a SQLite path vs a Postgres DSN.

No server needed — SQLAlchemy builds the engine lazily, so we can assert the
chosen dialect for both backends without connecting.
"""

from __future__ import annotations

from hop3_testing.results.store import make_store_engine, store_url
from hop3_testlab.config import TestlabConfig


def test_store_url_path_becomes_sqlite_dsn_passes_through():
    assert store_url("/data/x.db") == "sqlite:////data/x.db"
    dsn = "postgresql+psycopg://u@h:5432/db"
    assert store_url(dsn) == dsn  # a DSN is used as-is


def test_make_store_engine_picks_dialect(tmp_path):
    sqlite = make_store_engine(str(tmp_path / "x.db"))
    assert sqlite.dialect.name == "sqlite"
    # Built lazily — constructing a PG engine needs no running Postgres.
    pg = make_store_engine("postgresql+psycopg://u@h:5432/db")
    assert pg.dialect.name == "postgresql"


def test_store_target_prefers_dsn_over_sqlite(monkeypatch):
    monkeypatch.setenv("TESTLAB_DATABASE_URI", "postgresql+psycopg://x/db")
    assert TestlabConfig().STORE_TARGET == "postgresql+psycopg://x/db"
    monkeypatch.delenv("TESTLAB_DATABASE_URI")
    monkeypatch.setenv("TESTLAB_DB_PATH", "/data/y.db")
    assert TestlabConfig().STORE_TARGET == "/data/y.db"  # falls back to the file
