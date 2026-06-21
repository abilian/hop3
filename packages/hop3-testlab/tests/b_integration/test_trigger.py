# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""POST /runs/trigger spawns a run (full or per-app) or refuses when busy."""

from __future__ import annotations

from types import SimpleNamespace

from litestar.testing import TestClient

import hop3_testlab.web.controllers.runs as runs_ctl
from hop3_testlab import worker
from hop3_testlab.web.asgi import create_app


def _capture_spawn(monkeypatch):
    """Replace Popen with a recorder; return the list of spawned argv.

    Also stubs the per-trigger log file (no real ~/.hop3 write) and satisfies the
    blank-slate pre-flight by default so the happy-path tests aren't refused.
    """
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        runs_ctl.subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd)
    )
    monkeypatch.setattr(
        runs_ctl, "_open_trigger_log", lambda target: runs_ctl.subprocess.DEVNULL
    )
    monkeypatch.setattr(worker, "load_cloud_config", SimpleNamespace)
    # Pre-flight passes by default (SSH key resolves); the refuse test overrides.
    monkeypatch.setattr(worker, "_resolve_hetzner_ssh_key", lambda cfg: None)
    return spawned


def test_trigger_full_run_spawns_mode(monkeypatch):
    monkeypatch.setenv("TESTLAB_SCHEDULE_TARGET", "hetzner")
    spawned = _capture_spawn(monkeypatch)

    with TestClient(app=create_app()) as client:
        r = client.post("/runs/trigger", data={"mode": "ci"}, follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"] == "/?run=started"
    cmd = spawned[0]
    assert cmd[:3] == ["hop3-testlab", "run", "ci"]  # mode is positional
    assert cmd[cmd.index("--target") + 1] == "hetzner"
    assert cmd[3] == "--target"  # no app selector positional for a full-suite run


def test_trigger_per_app_spawns_apps(monkeypatch):
    spawned = _capture_spawn(monkeypatch)

    with TestClient(app=create_app()) as client:
        r = client.post(
            "/runs/trigger",
            data={"app": "apps/real-apps-docker/invoice-ninja"},
            follow_redirects=False,
        )

    assert r.status_code == 303
    cmd = spawned[0]
    # mode defaults to "ci"; the app is the positional selector after it.
    assert cmd[:4] == [
        "hop3-testlab",
        "run",
        "ci",
        "apps/real-apps-docker/invoice-ninja",
    ]


def test_trigger_refuses_full_suite_when_blank_slate_unresolvable(monkeypatch):
    # A full-suite hetzner run whose blank-slate SSH key can't be resolved must
    # REFUSE up-front and show why — never spawn a doomed run while falsely
    # reporting "started".
    monkeypatch.setenv("TESTLAB_SCHEDULE_TARGET", "hetzner")
    spawned = _capture_spawn(monkeypatch)

    def _boom(cfg):
        msg = "your key id_rsa.pub is not registered in your Hetzner project"
        raise RuntimeError(msg)

    monkeypatch.setattr(worker, "_resolve_hetzner_ssh_key", _boom)

    with TestClient(app=create_app()) as client:
        r = client.post("/runs/trigger", data={"mode": "ci"}, follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"].startswith("/?error=")
    assert "registered" in r.headers["location"]  # the real reason is surfaced
    assert spawned == []  # refused — nothing spawned, no fake "started"


def test_trigger_refuses_when_busy(monkeypatch):
    spawned = _capture_spawn(monkeypatch)
    # Hold the lease on the default target so the trigger sees it busy.
    from hop3_testlab import leasing
    from hop3_testlab.cloud_config import load_schedule
    from hop3_testlab.config import TestlabConfig
    from hop3_testlab.db import get_session_factory

    target = load_schedule().target
    with get_session_factory(str(TestlabConfig.get_instance().DB_PATH))() as s:
        leasing.try_acquire(s, target, "someone-else")

    with TestClient(app=create_app()) as client:
        r = client.post("/runs/trigger", data={"mode": "ci"}, follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"] == "/?run=busy"
    assert spawned == []  # nothing spawned while busy
