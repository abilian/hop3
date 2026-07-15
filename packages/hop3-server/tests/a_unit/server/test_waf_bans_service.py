# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the WafBansService background worker (ADR 050 §4).

Covers the thread lifecycle and the reconcile cycle's per-app isolation (a
broken app is rolled back and logged, never aborts the cycle or the others).
The ban scoring itself is tested in test_waf_wiring.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar, cast

from hop3.server import waf_bans_service
from hop3.server.waf_bans_service import WafBansService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session


class _MockSession:
    """A context-manager session that counts commit/rollback."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _StubRepo:
    apps: ClassVar[list] = []

    def __init__(self, **_kw) -> None:
        pass

    def list_all_ordered(self):
        return _StubRepo.apps


def _service(session, **kwargs) -> WafBansService:
    return WafBansService(cast("Callable[[], Session]", lambda: session), **kwargs)


def _patch(monkeypatch, apps, reconcile) -> None:
    _StubRepo.apps = apps
    monkeypatch.setattr(waf_bans_service, "AppRepository", _StubRepo)
    monkeypatch.setattr(waf_bans_service, "reconcile_bans", reconcile)
    # run_once loads AppConfig lazily; stub it so no real app dir is needed.
    monkeypatch.setattr(
        "hop3.project.config.AppConfig.from_dir", lambda _path: SimpleNamespace()
    )


def test_start_stop():
    # Long delays so no cycle fires during the lifecycle check.
    service = _service(_MockSession(), interval=100.0, initial_delay=100.0)
    service.start()
    assert service.is_running()
    service.stop()
    assert not service.is_running()


def test_run_once_sums_active_bans_and_commits_each_app(monkeypatch):
    session = _MockSession()
    apps = [
        SimpleNamespace(name="a", app_path="/a"),
        SimpleNamespace(name="b", app_path="/b"),
    ]
    seen: list[str] = []

    def reconcile(app, _cfg, _sess) -> int:
        seen.append(app.name)
        return 2 if app.name == "a" else 3

    _patch(monkeypatch, apps, reconcile)

    total = _service(session).run_once()

    assert total == 5
    assert seen == ["a", "b"]
    assert session.commits == 2  # committed per app
    assert session.rollbacks == 0


def test_run_once_isolates_a_failing_app(monkeypatch):
    session = _MockSession()
    apps = [
        SimpleNamespace(name="bad", app_path="/bad"),
        SimpleNamespace(name="ok", app_path="/ok"),
    ]

    def reconcile(app, _cfg, _sess) -> int:
        if app.name == "bad":
            msg = "boom"
            raise RuntimeError(msg)
        return 4

    _patch(monkeypatch, apps, reconcile)

    total = _service(session).run_once()  # must NOT raise

    assert total == 4  # the good app still counted
    assert session.rollbacks == 1  # the bad app rolled back
    assert session.commits == 1  # only the good app committed
