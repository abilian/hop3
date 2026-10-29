# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The REQUEST-scoped session: closed off the loop, never commits, never drops
a write without saying so.

The web scope ends after the response is sent, so the old finalizer's commit
could fail where nobody looks, and it committed even after the handler raised
(Dishka sends the handler's exception into the generator). A file database:
the checks read back through a second session.
"""

from __future__ import annotations

import threading

import anyio.to_thread
import pytest
from dishka.exceptions import ExitError
from dishka.integrations.litestar import FromDishka, inject, setup_dishka
from litestar import Litestar, post
from litestar.response import Redirect
from litestar.testing import TestClient
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from hop3.di import create_async_container, create_container, providers as di_providers
from hop3.di.providers import UncommittedChangesError
from hop3.orm import App, get_session_factory
from hop3.server.asgi import (
    UNSAVED_CHANGE_MESSAGE,
    refuse_uncommitted_writes,
    roll_back_on_exception,
)


@pytest.fixture(autouse=True)
def file_database(tmp_path, monkeypatch):
    monkeypatch.setenv("HOP3_DATABASE_URI", f"sqlite:///{tmp_path}/hop3.db")


def _stored_apps() -> list[str]:
    with get_session_factory()() as session:
        return [a.name for a in session.query(App).all()]


def test_a_committed_write_survives_the_scope():
    container = create_container()
    with container() as request:
        session = request.get(Session)
        session.add(App(name="kept"))
        session.commit()
    container.close()
    assert _stored_apps() == ["kept"]


@pytest.mark.parametrize("flush", [False, True])
def test_an_uncommitted_write_is_rolled_back_and_raised(flush):
    container = create_container()
    with pytest.raises(ExitError) as exc, container() as request:
        session = request.get(Session)
        session.add(App(name="forgotten"))
        if flush:  # a repository that flushes leaves nothing "new" behind
            session.flush()
    container.close()
    assert [type(e) for e in exc.value.exceptions] == [UncommittedChangesError]
    assert _stored_apps() == []


_RAW_WRITES = {
    "insert": lambda s: s.execute(insert(App).values(name="raw")),
    "update": lambda s: s.execute(update(App).values(name="renamed")),
    "delete": lambda s: s.execute(delete(App)),
    "connection": lambda s: s.connection().execute(insert(App).values(name="raw")),
}


@pytest.mark.parametrize("write", _RAW_WRITES.values(), ids=_RAW_WRITES)
def test_an_uncommitted_raw_statement_is_rolled_back_and_raised(write):
    """A Core statement writes without a flush; the guard sees it all the same."""
    with get_session_factory()() as setup:
        setup.add(App(name="kept"))
        setup.commit()
    container = create_container()
    with pytest.raises(ExitError) as exc, container() as request:
        write(request.get(Session))
    container.close()
    assert [type(e) for e in exc.value.exceptions] == [UncommittedChangesError]
    assert _stored_apps() == ["kept"]


def test_a_read_only_scope_is_not_an_error():
    container = create_container()
    with container() as request:
        request.get(Session).execute(select(App)).all()
    container.close()
    assert _stored_apps() == []


def test_a_committed_raw_statement_survives_the_scope():
    container = create_container()
    with container() as request:
        session = request.get(Session)
        session.execute(insert(App).values(name="raw"))
        session.commit()
    container.close()
    assert _stored_apps() == ["raw"]


def test_a_rolled_back_write_is_not_an_error():
    container = create_container()
    with container() as request:
        session = request.get(Session)
        session.add(App(name="refused"))
        session.flush()
        session.rollback()
    container.close()
    assert _stored_apps() == []


def test_a_failed_handler_reports_its_own_error_and_commits_nothing():
    container = create_container()
    with pytest.raises(LookupError), container() as request:
        request.get(Session).add(App(name="half-done"))
        raise LookupError
    container.close()
    assert _stored_apps() == []


@pytest.mark.anyio
async def test_the_web_scope_closes_its_session_off_the_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    closed_on: list[int] = []
    real_close = di_providers._close_request_session

    def _recording_close(session, handler_error):
        closed_on.append(threading.get_ident())
        real_close(session, handler_error)

    monkeypatch.setattr(di_providers, "_close_request_session", _recording_close)
    container = create_async_container()
    async with container() as request:
        session = await request.get(Session)
        session.add(App(name="web"))
        session.commit()
    await container.close()

    assert len(closed_on) == 1
    assert closed_on[0] != loop_thread
    assert _stored_apps() == ["web"]


# ---- through the web app: the browser must not be told it worked -----------


def _web_app():
    """A Litestar app wired like the real one: Dishka plus the response hook."""

    @post("/forget", status_code=303)
    @inject
    async def forget(session: FromDishka[Session]) -> Redirect:
        # Offloaded, as the real handlers do their database work.
        await anyio.to_thread.run_sync(session.add, App(name="forgotten"))
        return Redirect("/done", status_code=303)

    @post("/keep", status_code=303)
    @inject
    async def keep(session: FromDishka[Session]) -> Redirect:
        def write() -> None:
            session.add(App(name="kept"))
            session.commit()

        await anyio.to_thread.run_sync(write)
        return Redirect("/done", status_code=303)

    @post("/fail")
    @inject
    async def fail(session: FromDishka[Session]) -> None:
        await anyio.to_thread.run_sync(session.add, App(name="half-done"))
        await anyio.to_thread.run_sync(session.flush)
        msg = "the handler failed after writing"
        raise RuntimeError(msg)

    app = Litestar(
        route_handlers=[forget, keep, fail],
        after_request=refuse_uncommitted_writes,
        after_exception=[roll_back_on_exception],
    )
    setup_dishka(container=create_async_container(), app=app)
    return app


def test_a_handler_that_forgets_to_commit_answers_an_error_not_a_redirect():
    with TestClient(_web_app()) as client:
        response = client.post("/forget", follow_redirects=False)

    assert response.status_code == 500
    assert response.text == UNSAVED_CHANGE_MESSAGE
    assert _stored_apps() == []


def test_a_handler_that_commits_keeps_its_answer():
    with TestClient(_web_app()) as client:
        response = client.post("/keep", follow_redirects=False)

    assert response.status_code == 303
    assert _stored_apps() == ["kept"]


def test_a_handler_that_raises_after_writing_is_rolled_back_quietly():
    """
    Litestar answers the exception before the scope closes, so the scope used
    to find the writes pending and report a forgotten commit after the 500.
    """
    # A finalizer error escapes the app after the response: TestClient raises it.
    with TestClient(_web_app()) as client:
        response = client.post("/fail")

    assert response.status_code == 500
    assert _stored_apps() == []
