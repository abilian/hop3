# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dishka providers (mirrors ``hop3.di.providers``).

Scopes follow the playbook: ``Scope.APP`` for the config singleton; the
``Scope.REQUEST`` database session + repository providers are added with the
shared result store in the schema milestone (spec §8).
"""

from __future__ import annotations

from collections.abc import (
    Iterator,  # noqa: TC003 -- runtime: Dishka reads the return type
)

from dishka import Provider, Scope, provide
from sqlalchemy.orm import Session  # noqa: TC002 -- runtime: Dishka resolves it

from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import RunsRepository


class ConfigProvider(Provider):
    """APP-scoped: the Test Lab config singleton."""

    scope = Scope.APP

    @provide
    def config(self) -> TestlabConfig:
        return TestlabConfig.get_instance()


class DatabaseProvider(Provider):
    """REQUEST-scoped: a read session over the shared result store.

    Generator provider (playbook): the session is closed after the response.
    Reads don't commit, so there's no commit/rollback dance.
    """

    scope = Scope.REQUEST

    @provide
    def session(self, config: TestlabConfig) -> Iterator[Session]:
        factory = get_session_factory(str(config.DB_PATH))
        session = factory()
        try:
            yield session
        finally:
            session.close()


class RepositoryProvider(Provider):
    """REQUEST-scoped: repositories over the injected session."""

    scope = Scope.REQUEST

    @provide
    def runs(self, session: Session) -> RunsRepository:
        return RunsRepository(session)
