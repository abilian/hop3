# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Nightly scheduler: config precedence, the job wiring, and serve integration."""

from __future__ import annotations

import logging
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING

from hop3_testlab import scheduler
from hop3_testlab.cloud_config import load_schedule
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import BuildQueueRepository, ProfilesRepository
from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient

if TYPE_CHECKING:
    from pathlib import Path

_VARS = (
    "TESTLAB_SCHEDULE_ENABLED",
    "TESTLAB_SCHEDULE_HOUR",
    "TESTLAB_SCHEDULE_MINUTE",
    "TESTLAB_SCHEDULE_PROFILE",
    # NB: not TESTLAB_CONFIG — the conftest sets it to isolate tests from the
    # developer's ~/.hop3/testlab/config.toml; deleting it would re-read that.
)


def _clear(monkeypatch):
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)


def _session():
    return get_session_factory(TestlabConfig.get_instance().STORE_TARGET)()


def test_schedule_defaults(tmp_path: Path, monkeypatch):
    _clear(monkeypatch)
    s = load_schedule(tmp_path / "nope.toml")
    assert s.enabled is False  # off by default (no surprise nightly in dev)
    assert (s.hour, s.minute) == (0, 0)  # 00:00 local
    assert s.profile is None  # idle until a profile is configured


def test_schedule_from_toml(tmp_path: Path, monkeypatch):
    _clear(monkeypatch)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[schedule]\nenabled = true\nhour = 3\nminute = 30\nprofile = "nightly-suite"\n'
    )
    s = load_schedule(cfg)
    assert s.enabled is True
    assert (s.hour, s.minute) == (3, 30)
    assert s.profile == "nightly-suite"


def test_schedule_env_enable(tmp_path: Path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TESTLAB_SCHEDULE_ENABLED", "true")
    assert load_schedule(tmp_path / "nope.toml").enabled is True


def test_nightly_job_enqueues_configured_profile(monkeypatch):
    """The nightly enqueues its profile (the dispatcher then runs it) — no direct
    run, so it shares the single queue path with the UI's Start build."""
    with _session() as s:
        profile = ProfilesRepository(s).create(
            name="nightly-suite",
            source_name="m",
            source_url="u",
            source_ref="main",
            selection={"mode": "nightly"},
        )
        s.commit()
        pid = profile.id
    monkeypatch.setattr(
        scheduler, "load_schedule", lambda: SimpleNamespace(profile="nightly-suite")
    )

    scheduler._nightly_job()

    with _session() as s:
        pending = BuildQueueRepository(s).next_pending()
        assert pending is not None
        assert pending.profile_id == pid
        assert pending.actor == "nightly"


def test_nightly_job_idle_when_no_profile(monkeypatch, caplog):
    """No profile configured -> a loud, visible no-op (never a silent skip)."""
    monkeypatch.setattr(
        scheduler, "load_schedule", lambda: SimpleNamespace(profile=None)
    )
    with caplog.at_level("WARNING"):
        scheduler._nightly_job()
    assert "no [schedule].profile" in caplog.text
    with _session() as s:
        assert BuildQueueRepository(s).next_pending() is None  # nothing enqueued


def test_nightly_job_missing_profile_fails_loud(monkeypatch, caplog):
    """A configured-but-absent profile is logged loud, not silently dropped."""
    monkeypatch.setattr(
        scheduler, "load_schedule", lambda: SimpleNamespace(profile="ghost")
    )
    with caplog.at_level("ERROR"):
        scheduler._nightly_job()
    assert "not found" in caplog.text
    with _session() as s:
        assert BuildQueueRepository(s).next_pending() is None


def test_add_nightly_job_registers_cron(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler

    monkeypatch.setattr(
        scheduler,
        "load_schedule",
        lambda: SimpleNamespace(profile="nightly-suite", hour=0, minute=0),
    )
    sched = scheduler.add_nightly_job(BackgroundScheduler())
    sched.start(paused=True)  # register pending jobs without running them
    try:
        job = sched.get_job(scheduler.NIGHTLY_JOB_ID)
        assert job is not None
        assert "hour='0'" in str(job.trigger)
        assert "minute='0'" in str(job.trigger)
    finally:
        sched.shutdown(wait=False)


def test_dispatch_job_is_non_blocking_and_serial(monkeypatch):
    """The poll spawns the run on a worker thread and returns at once; while that
    thread is alive a second poll is a no-op (serial v1). This is what keeps
    apscheduler's max_instances=1 from skipping every tick (the warning flood)."""
    started = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def fake_dispatch(executor=None):
        calls.append(1)
        started.set()
        release.wait(timeout=5)
        return True

    monkeypatch.setattr("hop3_testlab.dispatcher.dispatch_once", fake_dispatch)
    scheduler._dispatch_thread = None  # isolate from any prior test's thread

    try:
        scheduler._dispatch_job()  # spawns the worker, returns immediately
        assert started.wait(timeout=2)  # the run is happening off-thread
        scheduler._dispatch_job()  # second poll while the run is still in flight
        assert calls == [1]  # ...is a no-op (serial v1)

        started.clear()
        release.set()  # let the first run finish
        scheduler._dispatch_thread.join(timeout=2)

        scheduler._dispatch_job()  # thread is done -> a new run starts
        assert started.wait(timeout=2)
        assert calls == [1, 1]
    finally:
        release.set()
        if scheduler._dispatch_thread is not None:
            scheduler._dispatch_thread.join(timeout=2)
        scheduler._dispatch_thread = None


def test_scheduler_quiets_apscheduler_info_noise():
    """Building a scheduler lifts apscheduler to WARNING — otherwise the 10s
    dispatch poll floods INFO ('Running job … executed successfully') every tick."""
    log = logging.getLogger("apscheduler")
    prev = log.level
    try:
        log.setLevel(logging.INFO)  # a noisy default
        scheduler.build_background_scheduler()
        assert log.level == logging.WARNING
    finally:
        log.setLevel(prev)


def test_serve_starts_and_stops_scheduler_when_enabled(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TESTLAB_SCHEDULE_ENABLED", "true")
    app = create_app()
    with TestClient(app=app):  # runs the Litestar lifespan (on_startup)
        assert app.state.scheduler.running
    assert not app.state.scheduler.running  # stopped on app shutdown


def test_serve_skips_scheduler_when_disabled(monkeypatch):
    _clear(monkeypatch)  # enabled defaults to False (DEBUG/UNSAFE stay on in tests)
    app = create_app()
    with TestClient(app=app):
        assert getattr(app.state, "scheduler", None) is None


def test_serve_runs_dispatcher_when_serving_for_real_even_with_nightly_off(monkeypatch):
    """The bug: a UI-triggered build sat 'pending' forever because the dispatch poll
    only ran when the nightly was enabled. In a real serve (not DEBUG/UNSAFE) the
    scheduler must run the dispatch poll even with the nightly disabled — and add no
    nightly job."""
    _clear(monkeypatch)  # nightly disabled
    monkeypatch.setenv("TESTLAB_DEBUG", "false")
    monkeypatch.setenv("TESTLAB_UNSAFE", "false")
    app = create_app()
    with TestClient(app=app):
        sched = app.state.scheduler
        assert sched.running
        job_ids = {job.id for job in sched.get_jobs()}
        assert scheduler.DISPATCH_JOB_ID in job_ids  # the queue is drained
        assert scheduler.NIGHTLY_JOB_ID not in job_ids  # but no auto-nightly
    assert not app.state.scheduler.running
