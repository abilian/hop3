# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration test fixtures for database testing."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine

from hop3.orm import User, get_session_factory, reset_session_factory_cache
from hop3.orm.session import BigIntAuditBase

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """
    Create test database engine (fresh for each test).

    Uses in-memory SQLite for fast, isolated tests.
    Each test gets a fresh database.

    Returns:
        SQLAlchemy engine bound to in-memory database
    """
    # Reset session factory cache to ensure clean state
    reset_session_factory_cache()

    # Use in-memory SQLite for testing
    database_uri = "sqlite:///:memory:"
    os.environ["HOP3_DATABASE_URI"] = database_uri

    engine = create_engine(database_uri, echo=False)

    # Create all tables
    with engine.begin() as conn:
        BigIntAuditBase.metadata.create_all(conn)

    yield engine

    # Cleanup
    engine.dispose()
    os.environ.pop("HOP3_DATABASE_URI", None)
    reset_session_factory_cache()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """
    Create test session for querying test results.

    This session shares the same in-memory database that get_session() uses
    via the session factory cache, so you can query the results of CLI commands.

    Args:
        db_engine: The test database engine

    Returns:
        SQLAlchemy Session for querying test state
    """
    session_factory = get_session_factory()
    session = session_factory()

    yield session

    session.close()


@pytest.fixture
def sample_user(db_session: Session) -> User:
    """
    Create sample user for tests.

    Args:
        db_session: Database session

    Returns:
        User instance with username 'testuser', role ``member`` (the default)
    """
    user = User(username="testuser", email="test@example.com")
    user.set_password("testpass123")
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)
    return user


@contextmanager
def get_session():
    """
    Context manager for getting a database session.

    This mimics the pattern used in the CLI commands for consistency.

    Yields:
        Database session
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
