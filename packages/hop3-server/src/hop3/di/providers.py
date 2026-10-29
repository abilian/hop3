# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[typing-only-third-party-import, typing-only-standard-library-import]

"""Dishka providers for Hop3 services."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from contextvars import ContextVar

import anyio.to_thread
from dishka import Provider, Scope, provide
from sqlalchemy import Connection, event
from sqlalchemy.orm import Session

from hop3.config import HopConfig
from hop3.core.backup import BackupManager
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
    EnvVarRepository,
    PortClaimRepository,
    RevokedTokenRepository,
    UserRepository,
)
from hop3.orm.session import get_session_factory
from hop3.platform.certificates import CertificatesManager


class ConfigProvider(Provider):
    """Provides configuration to the application."""

    scope = Scope.APP

    @provide
    def get_config(self) -> HopConfig:
        """
        Get or create the singleton config instance.

        Returns:
            HopConfig: The application configuration
        """
        return HopConfig.get_instance()


class UncommittedChangesError(RuntimeError):
    """A request scope ended with database writes nobody committed."""


#: ``Session.info`` key: set by a write statement, cleared by a commit or a
#: rollback.
_UNCOMMITTED = "hop3_uncommitted_writes"

#: The session the current web request opened. Each request runs in its own
#: task, so this never crosses requests. Read by the app's ``after_request``
#: hook, which answers an error instead of a success when writes are pending.
_REQUEST_SESSION: ContextVar[Session | None] = ContextVar(
    "hop3_request_session", default=None
)


def current_request_session() -> Session | None:
    """The session this web request opened through the container, if any."""
    return _REQUEST_SESSION.get()


def roll_back_if_uncommitted(session: Session) -> bool:
    """
    Roll back ``session``'s uncommitted writes; True if there were any.

    Blocking (a flush, a rollback): call it from a worker thread.
    """
    session.flush()  # turn pending objects into recorded writes
    if not session.info.get(_UNCOMMITTED, False):
        return False
    session.rollback()
    return True


def _open_request_session() -> Session:
    """
    A fresh session that remembers whether it holds uncommitted writes.

    Writes are seen on the connection, not in the ORM: ``after_execute`` on the
    connection of each transaction the session begins fires for every
    statement, so a flush, a ``session.execute(insert(...))`` / ``update`` /
    ``delete`` and a write through ``session.connection()`` are all marked
    alike. (``after_flush`` missed the last two; ``do_orm_execute`` misses the
    last one.) A ``text("UPDATE ...")`` is not recognised: a ``TextClause``
    does not say whether it writes.
    """
    session = get_session_factory()()
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

    The scope never commits: in the web app it ends after the response is
    sent, so a commit failing there could reach nobody, and an earlier
    version committed even after the handler had raised (Dishka sends the
    handler's exception into the generator; it does not throw it). Whoever
    writes commits (or rolls back) before answering. Writes still pending
    after a handler that succeeded are a handler bug: they are rolled back
    and the error is raised. After a failed handler they are just rolled
    back, so its own error is the one reported.
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
    Provides database sessions for REQUEST scope (synchronous containers).

    Each request/operation gets a fresh session, closed when the scope exits.
    The scope never commits; see ``_close_request_session``.
    """

    scope = Scope.REQUEST

    @provide
    def get_session(self, config: HopConfig) -> Iterator[Session]:
        """Yield a fresh session; close it when the request scope exits."""
        session = _open_request_session()
        handler_error = yield session
        _close_request_session(session, handler_error)


class AsyncDatabaseProvider(Provider):
    """
    The web app's REQUEST-scoped session, closed off the event loop.

    Dishka runs a sync generator's finalizer on the loop, and closing a
    SQLAlchemy session is blocking I/O (it returns the connection and rolls
    back), so the close runs in a worker thread, like the handlers' own work.
    """

    scope = Scope.REQUEST

    @provide
    async def get_session(self, config: HopConfig) -> AsyncIterator[Session]:
        """Yield a fresh session; close it in a worker thread on scope exit."""
        session = _open_request_session()
        token = _REQUEST_SESSION.set(session)
        try:
            handler_error = yield session
            await anyio.to_thread.run_sync(
                _close_request_session, session, handler_error
            )
        finally:
            _REQUEST_SESSION.reset(token)


class HopCoreProvider(Provider):
    """Provides Hop3 core services."""

    scope = Scope.APP

    # CertificatesManager is stateless, so APP scope is appropriate
    # It will be created once and reused throughout the application lifetime
    certificates_manager = provide(CertificatesManager)

    @provide(scope=Scope.REQUEST)
    def get_backup_manager(
        self,
        backup_repo: BackupRepository,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
    ) -> BackupManager:
        """
        Provide BackupManager instance.

        BackupManager requires repositories, so it uses REQUEST scope
        to get fresh repository instances for each request/operation.

        Dependencies:
            backup_repo: Repository for backup operations
            app_repo: Repository for app operations
            addon_credential_repo: Repository for addon credential operations

        Returns:
            BackupManager instance configured with the repositories
        """
        return BackupManager(
            backup_repo=backup_repo,
            app_repo=app_repo,
            addon_credential_repo=addon_credential_repo,
        )


#: The repositories a request can use, keyed by the attribute name a command
#: declares to receive one (``app_repo: AppRepository``). The single source:
#: `RepositoryProvider` provides every type here, and the RPC dispatcher
#: (server/controllers/rpc.py) injects by these attribute names.
REPOSITORY_TYPES: dict[str, type] = {
    "user_repo": UserRepository,
    "app_repo": AppRepository,
    "addon_credential_repo": AddonCredentialRepository,
    "backup_repo": BackupRepository,
    "env_var_repo": EnvVarRepository,
    "revoked_token_repo": RevokedTokenRepository,
    "port_claim_repo": PortClaimRepository,
}


def _repository_factory(repo_class: type) -> Callable[[Session], object]:
    """A Dishka factory building ``repo_class`` on the request's session."""

    def make(db_session: Session) -> object:
        return repo_class(session=db_session)

    return make


class RepositoryProvider(Provider):
    """
    Provides every repository in `REPOSITORY_TYPES`, REQUEST scope.

    Each repository wraps database operations for a specific model type on the
    request's session.
    """

    scope = Scope.REQUEST

    def __init__(self) -> None:
        super().__init__()
        for repo_class in REPOSITORY_TYPES.values():
            self.provide(_repository_factory(repo_class), provides=repo_class)
