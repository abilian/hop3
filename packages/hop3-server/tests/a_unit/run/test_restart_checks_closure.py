# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Every path that relaunches a uWSGI vassal must check the Nix closure first.

The closure guard originally lived only on `spawn_app`, which a *touch-restart*
never reached: restarting a RUNNING app touched the existing `.ini` so the
emperor recycled the vassal. That left the guard blind on the one sequence it was
written for (collect garbage, restart, exec a store path that is gone), and a
live run confirmed it: the closure was deleted, `hop3 app restart` returned 0,
and nothing was detected. A restart now stops the app and spawns it again; the
guard runs first, so a broken closure refuses the restart before the app stops.

These tests pin the call, not the implementation. They exist because "the guard
is installed" was believed once already, on the strength of a unit test that
asserted the guard's *absence* and passed.
"""

from __future__ import annotations

import pytest

from hop3.lib import Abort
from hop3.orm.app import App


class FakeApp:
    name = "forge"


@pytest.fixture
def refusing_guard(monkeypatch) -> list[str]:
    """Replace the closure check with one that always refuses, recording callers."""
    called: list[str] = []

    def fake(app) -> None:
        called.append(app.name)
        msg = "closure gone"
        raise Abort(msg)

    monkeypatch.setattr("hop3.orm.app.verify_nix_closure", fake)
    return called


class StoppableApp(FakeApp):
    """Records a stop, so "refused before stopping" can be asserted."""

    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def test_orm_restart_checks_closure_before_stopping(refusing_guard) -> None:
    """`App._restart_uwsgi` must refuse a broken closure while the app runs."""
    # Called unbound on a stand-in: the guard must run before anything reaches
    # the ORM or the config, so instrumenting a real App would only test that.
    app = StoppableApp()
    with pytest.raises(Abort):
        App._restart_uwsgi(app)

    assert refusing_guard == ["forge"]
    assert not app.stopped, "the app was stopped despite a broken closure"
