# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Regression test for DB connection-pool starvation during deploys.

Incident (cloud test, 2026-06-03): heavy app deploys ran in a background
thread that held the single SQLite connection open for the entire
multi-minute build. With ``pool_size=1, max_overflow=0`` that was the
ONLY connection, so every concurrent request — notably auth token
verification, which is a read — queued behind it and timed out after
``pool_timeout`` (30s), surfacing as bogus 401s on ``/rpc`` and 302s on
``/api/stream``. 18 of 19 app failures in that run traced to this.

The fix gives SQLite a real pool (pool_size=5/max_overflow=10); WAL mode
(already enabled) lets the read proceed on a second connection while the
"deploy" holds its write transaction open.

This test reproduces the scenario at the engine level: hold a write
transaction open on connection A, then read from connection B in another
thread. With the fix the read returns promptly; with the old
``pool_size=1`` config connection B can never be checked out and the
read thread stays blocked until the pool timeout — which this test
detects via a short join timeout.
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import text

from hop3.orm import get_session_factory, reset_session_factory_cache


@pytest.fixture
def file_db_factory(tmp_path):
    """A session factory bound to a real (file-based) SQLite DB.

    File-based is essential: WAL mode and the connection pool only apply
    to on-disk databases, not ``:memory:``.
    """
    reset_session_factory_cache()
    db_path = tmp_path / "pool-test.db"
    factory = get_session_factory(f"sqlite:///{db_path}")
    yield factory
    factory.kw["bind"].dispose()
    reset_session_factory_cache()


def test_sqlite_pool_is_not_size_one(file_db_factory) -> None:
    """SQLite must get a real pool, not the starvation-prone size-1 pool."""
    engine = file_db_factory.kw["bind"]
    # QueuePool.size() reports the configured pool_size.
    assert engine.pool.size() >= 2, (
        f"SQLite pool_size is {engine.pool.size()} — a single connection "
        "serializes all access and starves reads behind a held deploy "
        "transaction (the 2026-06-03 incident)."
    )


def test_read_not_starved_by_held_write_transaction(file_db_factory) -> None:
    """A read on a second connection must not block behind an open write.

    This is the exact shape of the incident: the deploy thread holds a
    write transaction open for minutes; an auth read must still succeed.
    """
    engine = file_db_factory.kw["bind"]

    # A scratch table so the test doesn't depend on the app schema.
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS scratch (x INTEGER)"))

    # Connection A: open a write transaction and DO NOT commit — this is
    # the deploy thread holding its connection across the build.
    conn_a = engine.connect()
    trans_a = conn_a.begin()
    conn_a.execute(text("INSERT INTO scratch VALUES (1)"))

    result: dict[str, object] = {}

    def read_on_second_connection() -> None:
        try:
            with engine.connect() as conn_b:
                count = conn_b.execute(text("SELECT count(*) FROM scratch")).scalar()
                result["count"] = count
        except Exception as exc:
            result["error"] = repr(exc)

    reader = threading.Thread(target=read_on_second_connection, daemon=True)
    reader.start()
    # With the fix the read returns in milliseconds. With pool_size=1 the
    # reader can never check out a connection and stays alive until the
    # ~30s pool timeout — so a 10s join cleanly distinguishes the two.
    reader.join(timeout=10.0)

    try:
        assert not reader.is_alive(), (
            "read thread blocked >10s behind a held write transaction — "
            "connection-pool starvation regression (pool_size too small)."
        )
        assert "error" not in result, f"read failed: {result.get('error')}"
        # WAL: the reader sees the last committed snapshot (0 rows), proving
        # it proceeded concurrently rather than waiting for A to commit.
        assert result.get("count") == 0
    finally:
        trans_a.rollback()
        conn_a.close()
        reader.join(timeout=5.0)
