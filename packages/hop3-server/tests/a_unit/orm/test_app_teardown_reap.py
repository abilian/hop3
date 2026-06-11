# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""ORM teardown must CONFIRM the app's processes/containers are actually gone.

Regression for the owncast 1935 reliability gap: `hop3 app stop`/`destroy` route
through ORM `app.stop()`, which used to only remove the uWSGI config (or
force-set STOPPED on a Docker timeout) and report STOPPED while the daemon —
and its fixed host port — lived on. Now stop reaps-and-verifies and refuses to
report STOPPED if anything survives.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.orm import App, AppStateEnum


class TestStopUwsgiReaps:
    def test_reports_stopped_when_processes_are_gone(self, monkeypatch):
        app = App(name="ghost-1")
        app.run_state = AppStateEnum.STOPPING  # skip the RUNNING->STOPPING path
        monkeypatch.setattr("hop3.run.reaper.reap_app_processes", lambda *a, **k: [])

        app._stop_uwsgi()

        assert app.run_state == AppStateEnum.STOPPED

    def test_raises_when_a_process_survives(self, monkeypatch):
        app = App(name="ghost-1")
        app.run_state = AppStateEnum.STOPPING
        monkeypatch.setattr("hop3.run.reaper.reap_app_processes", lambda *a, **k: [999])

        with pytest.raises(RuntimeError, match="still running"):
            app._stop_uwsgi()
        # It must NOT claim STOPPED while a process holds the port.
        assert app.run_state != AppStateEnum.STOPPED


class TestStopDockerVerifies:
    def _app(self) -> App:
        app = App(name="ghost-1")
        app.run_state = AppStateEnum.STOPPING
        app.runtime = "docker-compose"
        return app

    def test_reports_stopped_when_no_container_remains(self, monkeypatch):
        app = self._app()
        monkeypatch.setattr(
            "hop3.orm.app.subprocess.run",
            lambda *a, **k: SimpleNamespace(returncode=0, stderr="", stdout=""),
        )
        monkeypatch.setattr(App, "_app_container_ids", lambda self, **k: [])

        app._stop_docker_compose()

        assert app.run_state == AppStateEnum.STOPPED

    def test_raises_when_a_container_survives_stop_and_kill(self, monkeypatch):
        app = self._app()
        monkeypatch.setattr(
            "hop3.orm.app.subprocess.run",
            lambda *a, **k: SimpleNamespace(returncode=0, stderr="", stdout=""),
        )
        # Container keeps showing up even after the force-kill.
        monkeypatch.setattr(App, "_app_container_ids", lambda self, **k: ["c1"])

        with pytest.raises(RuntimeError, match="still"):
            app._stop_docker_compose()
        assert app.run_state != AppStateEnum.STOPPED
