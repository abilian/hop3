# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The Lab-owned tables: profiles, the server pool, and the build queue.

These exercise the real SQLite store (the testlab Base is created alongside the
result schema by `get_session_factory`), so they're integration, not unit.
"""

from __future__ import annotations

from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import (
    BuildQueueRepository,
    ProfilesRepository,
    ServersRepository,
)


def _session():
    return get_session_factory(str(TestlabConfig.get_instance().DB_PATH))()


def test_profile_crud_round_trip():
    with _session() as s:
        repo = ProfilesRepository(s)
        p = repo.create(
            name="nightly-main",
            source_name="main-repo",
            source_url="https://example.com/hop3.git",
            source_ref="main",
            platform_ref="main",
            selection={"tiers": ["fast"], "priorities": ["P0"]},
        )
        assert p.id is not None
        assert repo.get(p.id).source_ref == "main"
        assert [x.name for x in repo.list_all()] == ["nightly-main"]

        repo.update(p.id, source_ref="devel", platform_ref=None)
        s.refresh(p)
        assert p.source_ref == "devel"
        assert p.platform_ref is None
        assert p.selection["priorities"] == ["P0"]  # JSON round-trips

        assert repo.delete(p.id) is True
        assert repo.get(p.id) is None  # gone


def test_server_pool_crud_and_enabled_filter():
    with _session() as s:
        repo = ServersRepository(s)
        a = repo.create(name="docker-local", target_id="docker", kind="docker")
        b = repo.create(name="box-1", target_id="1.2.3.4", kind="ssh", enabled=False)
        assert a.enabled is True  # default

        assert {x.name for x in repo.list_all()} == {"docker-local", "box-1"}
        assert [x.name for x in repo.list_all(enabled_only=True)] == ["docker-local"]

        repo.update(b.id, enabled=True)
        s.refresh(b)
        assert {x.name for x in repo.list_all(enabled_only=True)} == {
            "docker-local",
            "box-1",
        }

        assert repo.delete(a.id) is True


def test_build_queue_fifo_and_transitions():
    with _session() as s:
        profiles = ProfilesRepository(s)
        queue = BuildQueueRepository(s)
        p = profiles.create(
            name="p1",
            source_name="main",
            source_url="u",
            source_ref="main",
            selection={},
        )

        r1 = queue.enqueue(p.id, actor="alice")
        r2 = queue.enqueue(p.id, actor="bob")

        # FIFO: oldest pending first.
        assert queue.next_pending().id == r1.id

        # Dispatch r1 -> r2 becomes the head.
        queue.mark(r1.id, "running", server_target_id="docker", run_uid="run-xyz")
        s.refresh(r1)
        assert r1.status == "running"
        assert r1.server_target_id == "docker"
        assert queue.next_pending().id == r2.id

        # Cancel a pending one; cancelling a running one is a no-op.
        assert queue.cancel(r2.id) is True
        assert queue.cancel(r1.id) is False
        assert queue.next_pending() is None  # nothing left queued

        assert {req.actor for req in queue.list_recent()} == {"alice", "bob"}
