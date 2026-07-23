# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
DB access over the shared hop3-testing result store.

The Test Lab reads/writes the *same* store the ``hop3-test`` CLI writes — one
store, two front-ends (ADR 044 §B/§D). The store is **SQLite** by default and
**Postgres** when ``TESTLAB_DATABASE_URI`` is set (a server-resident deploy); the
dialect-aware engine (PRAGMAs for SQLite, plain for Postgres) is shared with the
engine via ``hop3_testing.results.store.make_store_engine``.

The *result* schema is owned by ``ResultStore`` (its ``create_all`` +
``_ensure_columns``); the Lab's own tables (profiles / server pool / build queue)
live in the same store under their own ``Base`` and are created here.
"""

from __future__ import annotations

from functools import cache

from hop3_testing.results import ResultStore
from hop3_testing.results.store import make_store_engine
from sqlalchemy.orm import sessionmaker

from hop3_testlab.models import Base as TestlabBase


@cache
def get_session_factory(target: str) -> sessionmaker:
    """
    Cached sessionmaker for the result store ``target`` (a SQLite path or a
    Postgres DSN — pass ``TestlabConfig.STORE_TARGET``).
    """
    # Ensure the result schema exists (delegated to ResultStore so it never drifts).
    ResultStore(db_path=target)
    engine = make_store_engine(target)
    # The Lab's own tables live in the same store under their own Base (idempotent).
    TestlabBase.metadata.create_all(engine)
    _widen_build_detail(engine)
    return sessionmaker(bind=engine)


def _widen_build_detail(engine) -> None:
    """
    Widen ``testlab_build_request.detail`` from varchar(500) to text on existing
    Postgres deploys.

    ``create_all`` never alters an existing column, so a deploy created before this
    change keeps the 500-char cap that truncated build errors (and once overflowed,
    crashing the recorder). SQLite ignores varchar length (TEXT affinity), so this
    is a Postgres-only, idempotent, no-rewrite change. It runs here — before any
    detail is written through the cached factory — so the column is already text by
    the time the dispatcher records an outcome.
    """
    if engine.dialect.name != "postgresql":
        return
    from sqlalchemy import text  # ruff:ignore[import-outside-top-level]

    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE testlab_build_request ALTER COLUMN detail TYPE text")
        )
