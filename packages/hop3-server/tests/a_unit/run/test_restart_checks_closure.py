# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Every path that relaunches a uWSGI vassal must check the Nix closure first.

The closure guard originally lived only on `spawn_app`, which a *touch-restart*
never reaches: restarting a RUNNING app rewrites nothing and simply touches the
existing `.ini` so the emperor recycles the vassal. That left the guard blind on
the one sequence it was written for — collect garbage, restart, exec a store path
that is gone — and a live run confirmed it: the closure was deleted, `hop3 app
restart` returned 0, and nothing was detected.

These tests pin the call, not the implementation. They exist because "the guard
is installed" was believed once already, on the strength of a unit test that
asserted the guard's *absence* and passed.
"""

from __future__ import annotations

import pytest

from hop3.lib import Abort
from hop3.orm.app import App
from hop3.plugins.deploy.uwsgi.deployer import UWSGIDeployer


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
    monkeypatch.setattr("hop3.plugins.deploy.uwsgi.deployer.verify_nix_closure", fake)
    return called


@pytest.fixture
def no_touch(monkeypatch) -> list[str]:
    """Record every `.ini` touch, so "refused early" can be asserted."""
    touched: list[str] = []
    monkeypatch.setattr(
        "pathlib.Path.touch", lambda self, *a, **k: touched.append(str(self))
    )
    return touched


def test_orm_touch_restart_checks_closure_before_touching(
    refusing_guard, no_touch
) -> None:
    """`App._restart_uwsgi` must refuse a broken closure, and refuse it early."""
    # Called unbound on a stand-in: the guard must run before anything reaches
    # the ORM or the config, so instrumenting a real App would only test that.
    with pytest.raises(Abort):
        App._restart_uwsgi(FakeApp())

    assert refusing_guard == ["forge"]
    assert no_touch == [], "the .ini was touched despite a broken closure"


def test_deployer_touch_restart_checks_closure_before_touching(
    refusing_guard, no_touch
) -> None:
    """The uWSGI deployer's own restart is a second bypass, and needs the same check."""
    context = type("Ctx", (), {"app": FakeApp()})()
    deployer = UWSGIDeployer(context=context, artifact=None)

    with pytest.raises(Abort):
        deployer.restart()

    assert refusing_guard == ["forge"]
    assert no_touch == [], "the .ini was touched despite a broken closure"
