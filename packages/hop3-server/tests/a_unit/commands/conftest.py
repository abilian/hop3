# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pytest fixtures for command unit tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from hop3.orm import (
    App,
    AppRepository,
    EnvVar,
    get_session_factory,
    reset_session_factory_cache,
)

DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture
def engine():
    """Create a test database engine."""
    return create_engine(DATABASE_URI)


@pytest.fixture
def db_session(engine):
    """Create a test database session."""
    # Reset cache to ensure fresh database for each test
    reset_session_factory_cache()
    session_factory = get_session_factory(DATABASE_URI)

    with session_factory() as db_session:
        yield db_session

    # Clean up cache after test
    reset_session_factory_cache()


@pytest.fixture
def test_app(db_session):
    """Create a test app with some initial env vars."""
    app_repo = AppRepository(session=db_session)
    app = App(name="testapp")

    # Add some initial environment variables
    app.env_vars = [
        EnvVar(name="EXISTING_VAR", value="old_value", app=app),
        EnvVar(name="DEBUG", value="false", app=app),
    ]

    app_repo.add(app, auto_commit=True)
    return app
