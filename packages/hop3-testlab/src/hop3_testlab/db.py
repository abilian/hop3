# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Read-side DB access over the shared hop3-testing result store.

The Test Lab reads the *same* SQLite database the ``hop3-test`` CLI writes —
one store, two front-ends (ADR 044 §B/§D). Until the Postgres backend lands
(M0b), this opens a read engine on that file with ``check_same_thread=False`` +
WAL + ``busy_timeout``, mirroring ``hop3-server``'s ``orm/session.py`` so the web
app can read concurrently with CLI writes without locking errors.

Schema creation is delegated to ``ResultStore`` (its ``create_all`` +
``_ensure_columns``), so the read and write paths can never drift.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from hop3_testing.results import ResultStore
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def _configure_sqlite(dbapi_conn, _record) -> None:
    """Apply the same concurrency PRAGMAs hop3-server uses for SQLite."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


@cache
def get_session_factory(db_path: str) -> sessionmaker:
    """Return a cached sessionmaker for the result DB at ``db_path``."""
    path = Path(db_path)
    # Ensure the schema exists (reuses ResultStore.create_all + _ensure_columns,
    # and creates the parent dir) — the read path never owns the schema.
    ResultStore(db_path=path)
    engine = create_engine(
        f"sqlite:///{path}", connect_args={"check_same_thread": False}
    )
    event.listen(engine, "connect", _configure_sqlite)
    return sessionmaker(bind=engine)
