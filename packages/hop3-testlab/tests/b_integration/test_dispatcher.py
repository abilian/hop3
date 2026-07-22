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


def test_dispatch_requeues_when_run_loses_the_lease(monkeypatch):
    """A busy result (lost the lease in the TOCTOU window) requeues, not fails."""
    with _session() as s:
        p = _profile(s)
        ServersRepository(s).create(
            name="docker-local", target_id="docker", kind="docker"
        )
        req_id = BuildQueueRepository(s).enqueue(p.id).id
        s.commit()

    monkeypatch.setattr(dispatcher, "run_blockers", lambda _t, _a: None)
    monkeypatch.setattr(dispatcher, "run_once", lambda *a, **k: False)  # busy

    assert dispatcher.dispatch_once() is True
    with _session() as s:
        req = BuildQueueRepository(s).get(req_id)
        assert req.status == "pending"  # requeued, not failed
        assert req.server_target_id is None  # released for the next pick


def test_dispatch_sweeps_a_stale_running_build():
    """A build left running with no live lease (dispatcher died) is failed, not
    stuck running forever."""
    with _session() as s:
        p = _profile(s)
        queue = BuildQueueRepository(s)
        req = queue.enqueue(p.id)
        queue.mark(req.id, "running", server_target_id="docker")  # no lease held
        s.commit()
        req_id = req.id

    dispatcher.dispatch_once()  # _sweep_stale_running runs first
    with _session() as s:
        req = BuildQueueRepository(s).get(req_id)
        assert req.status == "failed"
        assert "dispatcher restarted" in req.detail


def test_dispatch_links_run_uid_to_build(monkeypatch):
    """A finished build is linked to the run it produced (via its build-<id> tag)."""
    from hop3_testing.results.models import TestRun

    with _session() as s:
        p = _profile(s)
        ServersRepository(s).create(
            name="docker-local", target_id="docker", kind="docker"
        )
        req_id = BuildQueueRepository(s).enqueue(p.id).id
        s.commit()
    with _session() as s:  # the run the build will produce, tagged by its trigger
        s.add(
            TestRun(
                run_uid="2026-run-xyz",
                trigger=f"build-{req_id}",
                mode="smoke",
                target_type="docker",
            )
        )
        s.commit()

    monkeypatch.setattr(dispatcher, "run_blockers", lambda _t, _a: None)
    monkeypatch.setattr(dispatcher, "run_once", lambda *a, **k: True)

    dispatcher.dispatch_once()
    with _session() as s:
        req = BuildQueueRepository(s).get(req_id)
        assert req.status == "done"
        assert req.run_uid == "2026-run-xyz"


def test_engine_exit_with_results_is_completed_not_crash(monkeypatch, tmp_path):
    """Engine exit 1 *after* recording results is a completed run with failing
    tests — not a crash. The build is FAILED, but the detail names the failing
    tests (the actionable signal) and carries none of the 'Engine exited'
    crash noise."""
    from hop3_testing.results.models import TestResultRecord, TestRun
    from hop3_testlab.worker import EngineExitError

    with _session() as s:
        p = _profile(s)
        ServersRepository(s).create(
            name="docker-local", target_id="docker", kind="docker"
        )
        req_id = BuildQueueRepository(s).enqueue(p.id).id
        s.commit()
    with _session() as s:  # the engine recorded a run + results, then exited 1
        run = TestRun(
            run_uid=f"run-completed-{req_id}",
            trigger=f"build-{req_id}",
            mode="broad",
            target_type="docker",
        )
        s.add(run)
        s.flush()
        s.add_all([
            TestResultRecord(run_id=run.id, test_name="forgejo", passed=False),
            TestResultRecord(run_id=run.id, test_name="discourse", passed=False),
            TestResultRecord(run_id=run.id, test_name="flask-hello", passed=True),
        ])
        s.commit()

    log = tmp_path / "engine.log"

    def _exit1(*_a, **_k):
        raise EngineExitError(1, log, f"Engine exited 1. See {log}")

    monkeypatch.setattr(dispatcher, "run_blockers", lambda _t, _a: None)
    monkeypatch.setattr(dispatcher, "run_once", _exit1)

    assert dispatcher.dispatch_once() is True
    with _session() as s:
        req = BuildQueueRepository(s).get(req_id)
        assert req.status == "failed"  # still red — never green for a failed run
        assert "2 of 3 test(s) failed" in req.detail
        assert "forgejo" in req.detail
        assert "discourse" in req.detail
        assert "Engine exited" not in req.detail  # not framed as a crash
        assert req.run_uid == f"run-completed-{req_id}"  # linked for the dashboard


def test_record_caps_overlong_crash_detail(monkeypatch, tmp_path):
    """A crash detail (the engine-log tail) longer than the detail column once
    overflowed ``varchar(500)`` and crashed the recorder thread *inside* _record
    (StringDataRightTruncation), leaving the build wedged for the orphan sweep to
    mislabel as "dispatcher restarted". _record must cap it so the outcome is
    always recorded. (SQLite doesn't enforce the width, so assert the cap directly.)"""
    from hop3_testlab.worker import EngineExitError

    with _session() as s:
        p = _profile(s)
        ServersRepository(s).create(
            name="docker-local", target_id="docker", kind="docker"
        )
        req_id = BuildQueueRepository(s).enqueue(p.id).id
        s.commit()

    log = tmp_path / "engine.log"
    long_msg = f"Engine exited 1. See {log}\n" + "boom " * 2000  # >> _DETAIL_MAX

    def _crash(*_a, **_k):  # no results recorded -> the uncapped crash path
        raise EngineExitError(1, log, long_msg)

    monkeypatch.setattr(dispatcher, "run_blockers", lambda _t, _a: None)
    monkeypatch.setattr(dispatcher, "run_once", _crash)

    assert dispatcher.dispatch_once() is True
    with _session() as s:
        req = BuildQueueRepository(s).get(req_id)
        assert req.status == "failed"
        assert len(req.detail) <= dispatcher._DETAIL_MAX  # capped — no overflow
        assert req.detail.endswith("…")
        assert req.detail.startswith("Engine exited 1")  # actionable prefix survives


def test_engine_exit_without_results_is_a_real_crash(monkeypatch, tmp_path):
    """Engine exit 1 with no recorded run/results is a genuine setup/deploy
    crash: keep the loud engine message (with the log path) as the reason."""
    from hop3_testlab.worker import EngineExitError

    with _session() as s:
        p = _profile(s)
        ServersRepository(s).create(
            name="docker-local", target_id="docker", kind="docker"
        )
        req_id = BuildQueueRepository(s).enqueue(p.id).id
        s.commit()

    log = tmp_path / "crash.log"

    def _exit1(*_a, **_k):
        raise EngineExitError(1, log, f"Engine exited 1. See {log}\nABORTED")

    monkeypatch.setattr(dispatcher, "run_blockers", lambda _t, _a: None)
    monkeypatch.setattr(dispatcher, "run_once", _exit1)

    assert dispatcher.dispatch_once() is True
    with _session() as s:
        req = BuildQueueRepository(s).get(req_id)
        assert req.status == "failed"
        assert "Engine exited 1" in req.detail  # the loud, log-pointing reason
