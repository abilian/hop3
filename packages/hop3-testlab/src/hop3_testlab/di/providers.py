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
    Iterator,  # ruff:ignore[typing-only-standard-library-import] -- runtime: Dishka reads the return type
)

from dishka import Provider, Scope, provide
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


class DatabaseProvider(Provider):
    """REQUEST-scoped: a session over the shared store.

    Generator provider (playbook): commit on success, roll back on exception,
    close in ``finally``. The dashboard reads (commit is a no-op); the profiles /
    servers / queue handlers write through it.
    """

    scope = Scope.REQUEST

    @provide
    def session(self, config: TestlabConfig) -> Iterator[Session]:
        factory = get_session_factory(config.STORE_TARGET)
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


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
