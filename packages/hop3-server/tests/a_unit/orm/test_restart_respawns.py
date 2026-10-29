# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`hop3 app restart` must bring the app's current settings to its processes.

A uWSGI vassal's `.ini` and its worker environment file are written at spawn.
Restart used to touch the existing `.ini`, so the emperor relaunched the vassal
with the values of its last spawn: a variable changed by `hop3 env set` never
reached the app, while `env set` said a restart would apply it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from hop3.orm import App, AppStateEnum


def test_restart_of_a_running_app_respawns_it_from_scratch(tmp_path, monkeypatch):
    enabled = tmp_path / "uwsgi-enabled"
    enabled.mkdir()
    (enabled / "web-1___web.1.ini").write_text("[uwsgi]\nenv = GREETING=old\n")
    config = SimpleNamespace(UWSGI_ENABLED=enabled)
    monkeypatch.setattr(
        "hop3.orm.app.HopConfig", SimpleNamespace(get_instance=lambda: config)
    )
    monkeypatch.setattr("hop3.orm.app.verify_nix_closure", lambda app: None)
    monkeypatch.setattr("hop3.run.reaper.reap_app_processes", lambda *a, **k: [])
    # What the spawn found in the emperor's directory when it ran.
    seen_by_spawn: list[list[str]] = []
    monkeypatch.setattr(
        "hop3.orm.app.spawn_app",
        lambda app: seen_by_spawn.append(sorted(p.name for p in enabled.iterdir())),
    )
    app = App(name="web-1", runtime="uwsgi")
    app.run_state = AppStateEnum.RUNNING
    app.last_deployed_at = datetime.now(UTC)

    app.restart()

    # Spawned once, after the vassal written with the old settings was gone.
    assert seen_by_spawn == [[]]
    assert app.run_state == AppStateEnum.STARTING
