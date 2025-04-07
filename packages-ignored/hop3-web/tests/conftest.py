# Copyright (c) 2021-2024, Abilian SAS & TCA
#
# SPDX-License-Identifier: AGPL-3.0-only

# ruff: noqa: E402
"""
Configuration and injectable fixtures for Pytest.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from hop3_web.web.main import create_app
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import scoped_session
from svcs.flask import container

if TYPE_CHECKING:
    from flask import Flask
    from flask.ctx import AppContext
    from flask.testing import FlaskClient
    from flask_sqlalchemy import SQLAlchemy

# Silence logging in tests
logger.configure(handlers=[])


class TestConfig:
    SECRET_KEY = "changeme"
    SECURITY_PASSWORD_SALT = "changeme"
    DEBUG = False
    DEBUG_TB_ENABLED = False

    SQLALCHEMY_DATABASE_URI: str

    def __init__(self):
        if db_uri := os.environ.get("TEST_DATABASE_URI"):
            self.SQLALCHEMY_DATABASE_URI = db_uri
        else:
            self.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
            # self.SQLALCHEMY_DATABASE_URI = "postgresql://localhost/aipress24_test"


#
# We usually only create an app once per session.
#
@pytest.fixture(scope="session")
def app() -> Flask:
    app = create_app(TestConfig())
    return app


@pytest.fixture
def app_context(app: Flask) -> Iterator[AppContext]:
    with app.app_context() as ctx:
        yield ctx


@pytest.fixture
def clean_database(app_context: AppContext) -> Iterator[SQLAlchemy]:
    """Return a fresh db for each test."""
    from app.flask.extensions import db as _db

    cleanup_db(_db)
    _db.create_all()
    yield _db

    _db.session.remove()
    cleanup_db(_db)


@pytest.fixture
def db(app_context: AppContext, app: Flask) -> Iterator[SQLAlchemy]:
    """Return a fresh db for each test."""
    from app.flask.extensions import db as _db

    cleanup_db(_db)
    _db.create_all()
    yield _db

    _db.session.remove()
    cleanup_db(_db)


@pytest.fixture
def db_session(clean_database) -> scoped_session:
    return container.get(scoped_session)


@pytest.fixture
def client(app: Flask, db_session: scoped_session) -> FlaskClient:
    """Return a Web client, used for testing, bound to a DB session."""
    return app.test_client()


#
# Cleanup utilities
#
def cleanup_db(db: SQLAlchemy) -> None:
    """Drop all the tables, in a way that doesn't raise integrity errors."""

    for table in reversed(db.metadata.sorted_tables):
        with contextlib.suppress(SQLAlchemyError):
            db.session.execute(table.delete())

    # db.drop_all()
    #
    # assert len(db.session.execute(text("SELECT * FROM pg_catalog.pg_tables")).all()) == 0
