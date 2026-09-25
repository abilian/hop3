# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Real accounts for tests that call the RPC endpoint over HTTP.

The dispatcher reads the caller's account from the database on every call
(ADR 061), so a token must name an account that exists, with the role the test
needs. The database is a file: the app answers requests on another thread, and
an in-memory SQLite database exists per connection, so the dispatcher would
read an empty one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.orm import User, get_session_factory, reset_session_factory_cache
from hop3.server.security.tokens import create_token

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from sqlalchemy.orm import Session

    from hop3.core.roles import Role


@pytest.fixture
def file_db(tmp_path: Path, monkeypatch) -> Iterator[Session]:
    """A file database the test and the app both open."""
    reset_session_factory_cache()
    monkeypatch.setenv("HOP3_DATABASE_URI", f"sqlite:///{tmp_path / 'hop3.db'}")
    session = get_session_factory()()
    yield session
    session.close()
    reset_session_factory_cache()


@pytest.fixture
def account(file_db: Session) -> Callable[..., str]:
    """Create an account with ``role`` and return a token naming it."""

    def make(username: str, role: Role, *, active: bool = True) -> str:
        user = User(
            username=username,
            email=f"{username}@example.com",
            password_hash="",
            role=role,
            active=active,
        )
        user.set_password("password123")
        file_db.add(user)
        file_db.commit()
        return create_token(username, scopes=["authenticated"])

    return make
