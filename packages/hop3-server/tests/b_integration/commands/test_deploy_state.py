# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A deploy's outcome must not depend on the deploy that ran before it.

After a deploy failed in proxy setup, the next deploy of the same app failed
once with "Cannot transition app from STOPPED to RUNNING", then worked. Two
sessions wrote the app's state. The request stopped the previous instance
(STARTING -> STOPPED) and committed only when it returned. By then the build
thread had loaded STARTING, moved it to STOPPED and back to STARTING, which
SQLAlchemy writes as no change, and it reloaded the request's STOPPED.

Two things were wrong, and each test here pins one: the hand-off to the build
thread did not commit first, and a failed deploy left STARTING behind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.commands import _deploy
from hop3.orm import App, AppStateEnum, get_session_factory
from hop3.server.streaming import get_stream

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session


def committed_state(app_id: int) -> tuple[AppStateEnum, str]:
    """The app's state as another session, the build thread's, sees it."""
    with get_session_factory()() as other:
        app = other.get(App, app_id)
        assert app is not None
        return app.run_state, app.error_message


@pytest.fixture
def app_left_starting(file_db: Session) -> App:
    """An app whose last deploy failed after STARTING was committed."""
    app = App(name="myapp", run_state=AppStateEnum.STARTING)
    file_db.add(app)
    file_db.commit()
    return app


class RecordingQueue:
    """A build queue that runs nothing, but notes what the thread would see."""

    workers = 2

    def __init__(self, app_id: int, *, run: bool = False) -> None:
        self.app_id = app_id
        self.run = run
        self.seen: tuple[AppStateEnum, str] | None = None

    def submit(self, job: Callable[[], None]) -> int:
        self.seen = committed_state(self.app_id)
        if self.run:
            job()
        return 0


def test_the_build_thread_starts_from_the_requests_stop(
    app_left_starting, file_db, monkeypatch
):
    app = app_left_starting
    app.mark_stopped()  # what stop_previous_instance does in the request
    queue = RecordingQueue(app.id)
    monkeypatch.setattr(_deploy, "get_build_queue", lambda: queue)

    _deploy.deploy_app_streaming(app, file_db)

    assert queue.seen is not None
    assert queue.seen[0] == AppStateEnum.STOPPED


def test_a_failed_deploy_leaves_the_app_failed_with_the_reason(
    app_left_starting, file_db, monkeypatch
):
    app = app_left_starting

    def fail(*_args, **_kwargs):
        msg = "nginx rejected the generated config"
        raise RuntimeError(msg)

    monkeypatch.setattr(_deploy, "do_deploy", fail)
    monkeypatch.setattr(
        _deploy, "get_build_queue", lambda: RecordingQueue(app.id, run=True)
    )

    result = _deploy.deploy_app_streaming(app, file_db)

    state, reason = committed_state(app.id)
    assert state == AppStateEnum.FAILED
    assert "nginx rejected the generated config" in reason
    assert not get_stream(result["stream_id"]).success


def test_an_earlier_failure_reason_is_kept(file_db):
    app = App(name="myapp", run_state=AppStateEnum.FAILED, error_message="the gate")
    file_db.add(app)
    file_db.commit()

    _deploy.record_deploy_failure(file_db, app.id, RuntimeError("a later message"))

    assert committed_state(app.id) == (AppStateEnum.FAILED, "the gate")
