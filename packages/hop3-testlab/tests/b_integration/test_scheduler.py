# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Nightly scheduler: config precedence, the job wiring, and serve integration."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from litestar.testing import TestClient

from hop3_testlab import scheduler
from hop3_testlab.cloud_config import load_schedule
from hop3_testlab.web.asgi import create_app

if TYPE_CHECKING:
    from pathlib import Path

_VARS = (
    "TESTLAB_SCHEDULE_ENABLED",
    "TESTLAB_SCHEDULE_TARGET",
    "TESTLAB_SCHEDULE_HOUR",
    "TESTLAB_SCHEDULE_MODE",
    # NB: not TESTLAB_CONFIG — the conftest sets it to isolate tests from the
    # developer's ~/.hop3/testlab/config.toml; deleting it would re-read that.
)


def _clear(monkeypatch):
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)


def test_schedule_defaults(tmp_path: Path, monkeypatch):
    _clear(monkeypatch)
    s = load_schedule(tmp_path / "nope.toml")
    assert s.enabled is False  # off by default (no surprise nightly in dev)
    assert s.target == "hetzner"
    assert (s.hour, s.minute) == (0, 0)  # 00:00 local
    assert s.mode == "nightly"


def test_schedule_from_toml(tmp_path: Path, monkeypatch):
    _clear(monkeypatch)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[schedule]\nenabled = true\ntarget = "docker"\nhour = 3\nminute = 30\n'
        'mode = "ci"\n'
    )
    s = load_schedule(cfg)
    assert s.enabled is True
    assert s.target == "docker"
    assert (s.hour, s.minute) == (3, 30)
    assert s.mode == "ci"


def test_schedule_env_enable(tmp_path: Path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TESTLAB_SCHEDULE_ENABLED", "true")
    assert load_schedule(tmp_path / "nope.toml").enabled is True


def test_nightly_job_runs_target_as_scheduled(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        scheduler,
        "load_schedule",
        lambda: SimpleNamespace(target="hetzner", mode="nightly"),
    )
    monkeypatch.setattr(
        scheduler, "run_once", lambda target, **kw: captured.update(target=target, **kw)
    )

    scheduler._nightly_job()

    assert captured == {
        "target": "hetzner",
        "trigger": "scheduled-nightly",
        "mode": "nightly",
    }


def test_add_nightly_job_registers_cron(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler

    monkeypatch.setattr(
        scheduler,
        "load_schedule",
        lambda: SimpleNamespace(target="hetzner", mode="nightly", hour=0, minute=0),
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


def test_serve_starts_and_stops_scheduler_when_enabled(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TESTLAB_SCHEDULE_ENABLED", "true")
    app = create_app()
    with TestClient(app=app):  # runs the Litestar lifespan (on_startup)
        assert app.state.scheduler.running
    assert not app.state.scheduler.running  # stopped on app shutdown


def test_serve_skips_scheduler_when_disabled(monkeypatch):
    _clear(monkeypatch)  # enabled defaults to False
    app = create_app()
    with TestClient(app=app):
        assert getattr(app.state, "scheduler", None) is None
