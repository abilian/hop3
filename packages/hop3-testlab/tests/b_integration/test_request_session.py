# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The REQUEST-scoped session: closed off the loop, never commits, never drops a
write without saying so.

Dishka sends the handler's exception into the provider's generator (it does
not throw it), so the old ``try: yield; commit / except: rollback`` committed
a failed request. The checks read back through a second session.
"""

from __future__ import annotations

import threading

import anyio.to_thread
import pytest
from dishka.exceptions import ExitError
from dishka.integrations.litestar import FromDishka, inject, setup_dishka
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.di import create_async_container, providers as di_providers
from hop3_testlab.di.providers import UncommittedChangesError
from hop3_testlab.models import Server
from hop3_testlab.web.asgi import (
    UNSAVED_CHANGE_MESSAGE,
    refuse_uncommitted_writes,
    roll_back_on_exception,
)
from litestar import Litestar, post
from litestar.response import Redirect
from litestar.testing import TestClient
from sqlalchemy import insert
from sqlalchemy.orm import Session

pytestmark = pytest.mark.anyio


def _stored_servers() -> list[str]:
    target = TestlabConfig.get_instance().STORE_TARGET
    with get_session_factory(target)() as session:
        return [s.name for s in session.query(Server).all()]


def _server(name: str) -> Server:
    return Server(name=name, target_id="docker", kind="docker")


async def test_a_committed_write_survives_the_scope():
    container = create_async_container()
    async with container() as request:
        session = await request.get(Session)
        session.add(_server("kept"))
        session.commit()
    await container.close()
    assert _stored_servers() == ["kept"]


async def test_the_scope_forgets_its_session_when_it_ends():
    """A closed session must not stay the context's "current request session"."""
    container = create_async_container()
    async with container() as request:
        session = await request.get(Session)
        assert di_providers.current_request_session() is session
    await container.close()
    assert di_providers.current_request_session() is None


_WRITES = {
    "pending": lambda s: s.add(_server("forgotten")),
    "flushed": lambda s: (s.add(_server("forgotten")), s.flush()),
    "raw": lambda s: s.execute(
        insert(Server).values(name="forgotten", target_id="docker", kind="docker")
    ),
}


@pytest.mark.parametrize("write", _WRITES.values(), ids=_WRITES)
async def test_an_uncommitted_write_is_rolled_back_and_raised(write):
    container = create_async_container()
    with pytest.raises(ExitError) as exc:
        async with container() as request:
            write(await request.get(Session))
    await container.close()
    assert [type(e) for e in exc.value.exceptions] == [UncommittedChangesError]
    assert _stored_servers() == []


async def test_a_failed_handler_reports_its_own_error_and_commits_nothing():
    container = create_async_container()
    with pytest.raises(LookupError):
        async with container() as request:
            (await request.get(Session)).add(_server("half-done"))
            raise LookupError
    await container.close()
    assert _stored_servers() == []


async def test_the_session_is_closed_off_the_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    closed_on: list[int] = []
    real_close = di_providers._close_request_session

    def _recording_close(session, handler_error):
        closed_on.append(threading.get_ident())
        real_close(session, handler_error)

    monkeypatch.setattr(di_providers, "_close_request_session", _recording_close)
    container = create_async_container()
    async with container() as request:
        await request.get(Session)
    await container.close()

    assert len(closed_on) == 1
    assert closed_on[0] != loop_thread


# ---- through the web app: the browser must not be told it worked -----------


def _web_app() -> Litestar:
    """A Litestar app wired like the Test Lab's: Dishka plus the two hooks."""

    @post("/forget", status_code=303)
    @inject
    async def forget(session: FromDishka[Session]) -> Redirect:
        await anyio.to_thread.run_sync(session.add, _server("forgotten"))
        return Redirect("/done", status_code=303)

    @post("/fail")
    @inject
    async def fail(session: FromDishka[Session]) -> None:
        await anyio.to_thread.run_sync(session.add, _server("half-done"))
        await anyio.to_thread.run_sync(session.flush)
        msg = "the handler failed after writing"
        raise RuntimeError(msg)

    app = Litestar(
        route_handlers=[forget, fail],
        after_request=refuse_uncommitted_writes,
        after_exception=[roll_back_on_exception],
    )
    setup_dishka(container=create_async_container(), app=app)
    return app


@pytest.mark.parametrize("anyio_backend", ["asyncio"])
def test_a_handler_that_forgets_to_commit_answers_an_error(anyio_backend):
    with TestClient(_web_app()) as client:
        response = client.post("/forget", follow_redirects=False)

    assert response.status_code == 500
    assert response.text == UNSAVED_CHANGE_MESSAGE
    assert _stored_servers() == []


@pytest.mark.parametrize("anyio_backend", ["asyncio"])
def test_a_handler_that_raises_after_writing_is_rolled_back_quietly(anyio_backend):
    # A finalizer error escapes the app after the response: TestClient raises it.
    with TestClient(_web_app()) as client:
        response = client.post("/fail")

    assert response.status_code == 500
    assert _stored_servers() == []
