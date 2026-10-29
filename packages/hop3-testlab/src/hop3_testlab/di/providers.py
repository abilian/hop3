# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Dishka providers (mirrors ``hop3.di.providers``).

Scopes follow the playbook: ``Scope.APP`` for the config singleton; the
``Scope.REQUEST`` database session + repository providers are added with the
shared result store in the schema milestone (spec §8).
"""

from __future__ import annotations

from collections.abc import (
    AsyncIterator,  # ruff:ignore[typing-only-standard-library-import] -- runtime: Dishka reads the return type
)
from contextvars import ContextVar

import anyio.to_thread
from dishka import Provider, Scope, provide
from sqlalchemy import Connection, event
from sqlalchemy.orm import (
    Session,  # ruff:ignore[typing-only-third-party-import] -- runtime: Dishka resolves it
)

from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import (
    BuildQueueRepository,
    CredentialsRepository,
    ProfilesRepository,
    RunsRepository,
    ServersRepository,
)


class ConfigProvider(Provider):
    """APP-scoped: the Test Lab config singleton."""

    scope = Scope.APP

    @provide
    def config(self) -> TestlabConfig:
        return TestlabConfig.get_instance()


class UncommittedChangesError(RuntimeError):
    """A request scope ended with database writes nobody committed."""


#: ``Session.info`` key: set by a write statement, cleared by a commit or a
#: rollback.
_UNCOMMITTED = "hop3_testlab_uncommitted_writes"

#: The session the current web request opened (each request is its own task).
#: Read by the app's hooks: ``after_request`` answers an error instead of a
#: success when writes are pending, ``after_exception`` rolls back. Under
#: Litestar the scope's own finalizer only runs after the response is sent,
#: and never learns that the handler raised.
_REQUEST_SESSION: ContextVar[Session | None] = ContextVar(
    "hop3_testlab_request_session", default=None
)


def current_request_session() -> Session | None:
    """The session this web request opened through the container, if any."""
    return _REQUEST_SESSION.get()


def roll_back_if_uncommitted(session: Session) -> bool:
    """
    Roll back ``session``'s uncommitted writes; True if there were any.

    Blocking (a flush, a rollback): call it from a worker thread.
    """
    session.flush()
    if not session.info.get(_UNCOMMITTED, False):
        return False
    session.rollback()
    return True


def _open_request_session(config: TestlabConfig) -> Session:
    """
    A fresh session that remembers whether it holds uncommitted writes.

    Writes are seen on the connection (``after_execute`` on each transaction's
    connection), so a flush, a Core ``insert``/``update``/``delete`` and a
    write through ``session.connection()`` are all marked alike. A
    ``text("UPDATE ...")`` is not recognised: a ``TextClause`` does not say
    whether it writes. Same mechanism as ``hop3.di.providers``.
    """
    session = get_session_factory(config.STORE_TARGET)()
    event.listen(session, "after_begin", _watch_connection)
    event.listen(session, "after_commit", _clear_uncommitted)
    event.listen(session, "after_rollback", _clear_uncommitted)
    return session


def _watch_connection(
    session: Session, _transaction: object, connection: Connection
) -> None:
    """Mark ``session`` on every write ``connection`` executes."""

    def mark_if_write(_conn: Connection, clause: object, *_args: object) -> None:
        if getattr(clause, "is_dml", False):
            session.info[_UNCOMMITTED] = True

    event.listen(connection, "after_execute", mark_if_write)


def _clear_uncommitted(session: Session) -> None:
    session.info.pop(_UNCOMMITTED, None)


def _close_request_session(
    session: Session, handler_error: BaseException | None
) -> None:
    """
    Close a request's session; refuse to drop writes without saying so.

    The scope never commits. Dishka *sends* the handler's exception into the
    generator (it does not throw it), so an ``except`` around ``yield`` never
    ran and a failed request was committed by the finalizer; and the scope
    ends after the response is sent, so a failing commit there reached nobody.
    Whoever writes commits before answering. Writes still pending after a
    handler that succeeded are a handler bug: rolled back, and raised. After a
    failed handler they are just rolled back, so its own error is reported.
    """
    if handler_error is not None:
        session.close()
        return
    try:
        session.flush()  # turn pending objects into recorded writes
        uncommitted = session.info.get(_UNCOMMITTED, False)
    finally:
        session.close()
    if uncommitted:
        msg = (
            "a request scope ended with uncommitted database writes, now rolled "
            "back: the handler must commit (or roll back) before it responds"
        )
        raise UncommittedChangesError(msg)


class DatabaseProvider(Provider):
    """
    REQUEST-scoped: a session over the shared store, closed off the event loop.

    The scope never commits (see ``_close_request_session``): a handler that
    writes injects the ``Session`` and commits before it responds. Closing a
    session is blocking I/O, so it runs in a worker thread.
    """

    scope = Scope.REQUEST

    @provide
    async def session(self, config: TestlabConfig) -> AsyncIterator[Session]:
        session = _open_request_session(config)
        token = _REQUEST_SESSION.set(session)
        try:
            handler_error = yield session
            await anyio.to_thread.run_sync(
                _close_request_session, session, handler_error
            )
        finally:
            _REQUEST_SESSION.reset(token)


class RepositoryProvider(Provider):
    """REQUEST-scoped: repositories over the injected session."""

    scope = Scope.REQUEST

    @provide
    def runs(self, session: Session) -> RunsRepository:
        return RunsRepository(session)

    @provide
    def profiles(self, session: Session) -> ProfilesRepository:
        return ProfilesRepository(session)

    @provide
    def servers(self, session: Session) -> ServersRepository:
        return ServersRepository(session)

    @provide
    def credentials(self, session: Session) -> CredentialsRepository:
        return CredentialsRepository(session)

    @provide
    def queue(self, session: Session) -> BuildQueueRepository:
        return BuildQueueRepository(session)
