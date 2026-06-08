# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""POST /runs/trigger spawns a run (full or per-app) or refuses when busy."""

from __future__ import annotations

import hop3_testlab.web.controllers.runs as runs_ctl
from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient


def _capture_spawn(monkeypatch):
    """Replace Popen with a recorder; return the list of spawned argv."""
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        runs_ctl.subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd)
    )
    return spawned


def test_trigger_full_run_spawns_mode(monkeypatch):
    monkeypatch.setenv("TESTLAB_SCHEDULE_TARGET", "hetzner")
    spawned = _capture_spawn(monkeypatch)

    with TestClient(app=create_app()) as client:
        r = client.post("/runs/trigger", data={"mode": "ci"}, follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"] == "/?run=started"
    cmd = spawned[0]
    assert cmd[:2] == ["hop3-testlab", "run"]
    assert cmd[cmd.index("--mode") + 1] == "ci"
    assert cmd[cmd.index("--target") + 1] == "hetzner"
    assert "--apps" not in cmd


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
    assert cmd[cmd.index("--apps") + 1] == "apps/real-apps-docker/invoice-ninja"
    assert "--mode" not in cmd


def test_trigger_refuses_when_busy(monkeypatch):
    spawned = _capture_spawn(monkeypatch)
    # Hold the lease on the default target so the trigger sees it busy.
    from hop3_testlab import leasing  # noqa: PLC0415
    from hop3_testlab.cloud_config import load_schedule  # noqa: PLC0415
    from hop3_testlab.config import TestlabConfig  # noqa: PLC0415
    from hop3_testlab.db import get_session_factory  # noqa: PLC0415

    target = load_schedule().target
    with get_session_factory(str(TestlabConfig.get_instance().DB_PATH))() as s:
        leasing.try_acquire(s, target, "someone-else")

    with TestClient(app=create_app()) as client:
        r = client.post("/runs/trigger", data={"mode": "ci"}, follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"] == "/?run=busy"
    assert spawned == []  # nothing spawned while busy
