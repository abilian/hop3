# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The live current-run panel: idle, running (progress + ETA), and stop."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from hop3_testing.results import ResultStore
from hop3_testing.results.models import RunLease, TestRun
from hop3_testlab.repositories import RunsRepository
from hop3_testlab.web import controllers
from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from pathlib import Path


def _engine(db_path: Path):
    ResultStore(db_path=db_path)  # ensure schema (incl. run_lease.pid)
    return create_engine(f"sqlite:///{db_path}")


def _seed_running(db_path: Path, *, pid: int | None = 4242) -> None:
    """A live lease + an in-flight run + one completed run for the ETA history."""
    engine = _engine(db_path)
    now = time.time()
    with Session(engine) as s:
        # History: a finished nightly/docker run (~100s, 10 tests) -> the ETA basis.
        s.add(
            TestRun(
                run_uid="2026-06-06T00-00-00Z-docker-old",
                mode="nightly",
                target_type="docker",
                target_name="docker",
                started_at=datetime.now(UTC) - timedelta(seconds=200),
                finished_at=datetime.now(UTC) - timedelta(seconds=100),
                total_tests=10,
                passed_tests=10,
                failed_tests=0,
            )
        )
        # In-flight: 5 of ~10 done, no finished_at yet.
        s.add(
            TestRun(
                run_uid="2026-06-07T00-00-00Z-docker-live",
                mode="nightly",
                target_type="docker",
                target_name="docker",
                started_at=datetime.now(UTC) - timedelta(seconds=30),
                finished_at=None,
                total_tests=5,
                passed_tests=5,
                failed_tests=0,
            )
        )
        s.add(
            RunLease(
                target_id="docker",
                holder="cli",
                run_uid=None,
                acquired_at=now,
                expires_at=now + 3600,
                pid=pid,
            )
        )
        s.commit()


def test_panel_is_idle_when_nothing_runs(tmp_path):
    _engine(tmp_path / "test-results.db")  # schema only, no lease
    with TestClient(app=create_app()) as client:
        r = client.get("/running")
    assert r.status_code == 200
    assert "No run in progress" in r.text


def test_panel_shows_progress_and_eta_when_running(tmp_path):
    _seed_running(tmp_path / "test-results.db")
    with TestClient(app=create_app()) as client:
        r = client.get("/running")
    assert r.status_code == 200
    assert "Running on" in r.text
    assert "docker" in r.text
    assert "5" in r.text  # tests done so far
    assert "Stop run" in r.text  # stop control present (pid recorded)


def test_panel_shows_starting_before_the_run_row_exists(tmp_path):
    db = tmp_path / "test-results.db"
    _engine(db)
    now = time.time()
    with Session(_engine(db)) as s:  # lease held, but no TestRun yet
        s.add(
            RunLease(
                target_id="docker",
                holder="cli",
                acquired_at=now,
                expires_at=now + 3600,
                pid=999,
            )
        )
        s.commit()
    with TestClient(app=create_app()) as client:
        r = client.get("/running")
    assert r.status_code == 200
    assert "starting" in r.text.lower()


def test_stop_kills_engine_marks_aborted_and_frees_lease(tmp_path, monkeypatch):
    db = tmp_path / "test-results.db"
    _seed_running(db, pid=4242)

    killed: list[int] = []
    monkeypatch.setattr(
        controllers.running,
        "terminate_engine",
        lambda pid, starttime=None: killed.append(pid),
    )

    with TestClient(app=create_app()) as client:
        r = client.post("/running/stop")
    assert r.status_code in {200, 201}
    assert "No run in progress" in r.text  # panel now idle

    assert killed == [4242]  # the engine's process group was signalled

    with Session(_engine(db)) as s:
        run = (
            s.query(TestRun).filter_by(run_uid="2026-06-07T00-00-00Z-docker-live").one()
        )
        assert run.finished_at is not None  # marked finished
        assert (run.run_metadata or {}).get("aborted") is True
        assert s.query(RunLease).count() == 0  # lease released


def test_swept_orphan_no_longer_masquerades_as_the_live_run(tmp_path):
    """
    A run left unfinished by a prior crash/Stop must not show as the live run
    under the next lease — active_run() picks the newest unfinished row, so the
    sweep is what keeps it from latching onto a stale orphan.
    """
    db = tmp_path / "test-results.db"
    engine = _engine(db)
    with Session(engine) as s:
        s.add(
            TestRun(
                run_uid="2026-06-01T00-00-00Z-docker-orphan",
                mode="nightly",
                target_type="docker",
                target_name="docker",
                started_at=datetime.now(UTC) - timedelta(hours=2),
                finished_at=None,  # killed mid-flight; never stamped
                total_tests=3,
                passed_tests=3,
                failed_tests=0,
            )
        )
        s.commit()

    with Session(engine) as s:
        repo = RunsRepository(s)
        assert repo.active_run() is not None  # the bug: orphan looks live
        assert repo.sweep_orphans() == 1
        assert repo.active_run() is None  # fixed: nothing masquerades

    with Session(engine) as s:
        orphan = (
            s
            .query(TestRun)
            .filter_by(run_uid="2026-06-01T00-00-00Z-docker-orphan")
            .one()
        )
        assert orphan.finished_at is not None  # now finished, not in-flight
        assert (orphan.run_metadata or {}).get("aborted") is True


def test_stop_when_idle_is_harmless(tmp_path, monkeypatch):
    _engine(tmp_path / "test-results.db")
    killed: list[int] = []
    monkeypatch.setattr(
        controllers.running,
        "terminate_engine",
        lambda pid, starttime=None: killed.append(pid),
    )
    with TestClient(app=create_app()) as client:
        r = client.post("/running/stop")
    assert r.status_code in {200, 201}
    assert "No run in progress" in r.text
    assert killed == []  # nothing was running, so nothing to kill
