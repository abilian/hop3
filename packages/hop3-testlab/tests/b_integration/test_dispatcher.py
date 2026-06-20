# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The dispatcher: queued builds go to a free pool server (the user never picks).

Stubs `run_once`/`run_blockers` (the dispatcher's seams) so these exercise the
queue + pool + status logic against the real SQLite store, not a real run.
"""

from __future__ import annotations

from hop3_testlab import dispatcher, leasing
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import (
    BuildQueueRepository,
    ProfilesRepository,
    ServersRepository,
)


def _session():
    return get_session_factory(str(TestlabConfig.get_instance().DB_PATH))()


def _profile(s, **over):
    fields = {
        "name": "p1",
        "source_name": "main",
        "source_url": "u",
        "source_ref": "main",
        "selection": {"mode": "smoke"},
    }
    fields.update(over)
    return ProfilesRepository(s).create(**fields)


def test_dispatch_noop_when_queue_empty(monkeypatch):
    monkeypatch.setattr(dispatcher, "run_once", lambda *a, **k: True)
    assert dispatcher.dispatch_once() is False


def test_dispatch_runs_pending_on_free_server(monkeypatch):
    with _session() as s:
        p = _profile(s)
        ServersRepository(s).create(
            name="docker-local", target_id="docker", kind="docker"
        )
        req_id = BuildQueueRepository(s).enqueue(p.id, actor="alice").id
        s.commit()

    calls: list[tuple] = []
    monkeypatch.setattr(dispatcher, "run_blockers", lambda _t, _a: None)
    monkeypatch.setattr(
        dispatcher, "run_once", lambda target, **kw: calls.append((target, kw)) or True
    )

    assert dispatcher.dispatch_once() is True
    assert calls[0][0] == "docker"  # ran on the pool server
    spec = calls[0][1]["spec"]
    assert spec.source_ref == "main"
    assert spec.selection == {"mode": "smoke"}  # rule-based, not a list
    with _session() as s:
        assert BuildQueueRepository(s).get(req_id).status == "done"


def test_dispatch_picks_a_free_server_when_one_is_busy(monkeypatch):
    with _session() as s:
        p = _profile(s, selection={})
        ServersRepository(s).create(name="a", target_id="hostA", kind="ssh")
        ServersRepository(s).create(name="b", target_id="hostB", kind="ssh")
        leasing.try_acquire(s, "hostA", "someone-else")  # A is busy
        BuildQueueRepository(s).enqueue(p.id)
        s.commit()

    targets: list[str] = []
    monkeypatch.setattr(dispatcher, "run_blockers", lambda _t, _a: None)
    monkeypatch.setattr(
        dispatcher, "run_once", lambda target, **kw: targets.append(target) or True
    )

    assert dispatcher.dispatch_once() is True
    assert targets == ["hostB"]  # the queue picked the free server


def test_dispatch_leaves_pending_when_all_servers_busy(monkeypatch):
    with _session() as s:
        p = _profile(s)
        ServersRepository(s).create(
            name="docker-local", target_id="docker", kind="docker"
        )
        leasing.try_acquire(s, "docker", "someone-else")  # the only server is busy
        req_id = BuildQueueRepository(s).enqueue(p.id).id
        s.commit()

    ran: list[int] = []
    monkeypatch.setattr(dispatcher, "run_once", lambda *a, **k: ran.append(1) or True)

    assert dispatcher.dispatch_once() is False  # nothing free — leave it queued
    assert ran == []
    with _session() as s:
        assert BuildQueueRepository(s).get(req_id).status == "pending"


def test_dispatch_marks_failed_when_pre_flight_blocks(monkeypatch):
    with _session() as s:
        p = _profile(s)
        ServersRepository(s).create(name="hz", target_id="hetzner", kind="hetzner")
        req_id = BuildQueueRepository(s).enqueue(p.id).id
        s.commit()

    ran: list[int] = []
    monkeypatch.setattr(
        dispatcher, "run_blockers", lambda _t, _a: "Can't start: unauthorized"
    )
    monkeypatch.setattr(dispatcher, "run_once", lambda *a, **k: ran.append(1) or True)

    assert dispatcher.dispatch_once() is True
    assert ran == []  # doomed run refused, not spawned
    with _session() as s:
        req = BuildQueueRepository(s).get(req_id)
        assert req.status == "failed"
        assert "unauthorized" in req.detail  # actionable reason recorded


def test_dispatch_marks_failed_when_run_crashes(monkeypatch):
    with _session() as s:
        p = _profile(s)
        ServersRepository(s).create(
            name="docker-local", target_id="docker", kind="docker"
        )
        req_id = BuildQueueRepository(s).enqueue(p.id).id
        s.commit()

    def _boom(*_a, **_k):
        msg = "deploy blew up"
        raise RuntimeError(msg)

    monkeypatch.setattr(dispatcher, "run_blockers", lambda _t, _a: None)
    monkeypatch.setattr(dispatcher, "run_once", _boom)

    assert dispatcher.dispatch_once() is True
    with _session() as s:
        req = BuildQueueRepository(s).get(req_id)
        assert req.status == "failed"
        assert "deploy blew up" in req.detail
