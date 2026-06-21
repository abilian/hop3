# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Postgres store smoke — gated on a real Postgres (TESTLAB_PG_DSN).

Skipped when unset (local/CI without PG); where a PG is available it proves the
schema (result tables + the Lab's own tables) creates and round-trips on Postgres
via the same `get_session_factory` path the app uses.

Run: TESTLAB_PG_DSN=postgresql+psycopg://user:pw@host/db pytest tests/c_e2e/test_pg_store.py
"""

from __future__ import annotations

import os

import pytest

from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import (
    BuildQueueRepository,
    ProfilesRepository,
    ServersRepository,
)

PG_DSN = os.environ.get("TESTLAB_PG_DSN")

pytestmark = pytest.mark.skipif(
    not PG_DSN, reason="set TESTLAB_PG_DSN to run the Postgres store smoke"
)


def test_postgres_schema_creates_and_round_trips():
    get_session_factory.cache_clear()
    factory = get_session_factory(PG_DSN)
    try:
        with factory() as s:
            profiles = ProfilesRepository(s)
            servers = ServersRepository(s)
            queue = BuildQueueRepository(s)

            p = profiles.create(
                name="pg-smoke",
                source_name="m",
                source_url="u",
                source_ref="main",
                selection={"mode": "smoke"},
            )
            servers.create(name="pg-docker", target_id="docker", kind="docker")
            req = queue.enqueue(p.id, actor="pg")
            s.commit()

            assert profiles.get(p.id).selection == {"mode": "smoke"}  # JSON on PG
            assert queue.next_pending().id == req.id

            # cleanup so re-runs are idempotent
            queue.cancel(req.id)
            profiles.delete(p.id)
            for srv in servers.list_all():
                servers.delete(srv.id)
            s.commit()
    finally:
        get_session_factory.cache_clear()
