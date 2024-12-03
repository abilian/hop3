# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from hop3.orm import App, AppRepository, EnvVar, get_session_factory

DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture
def engine():
    return create_engine(DATABASE_URI)


@pytest.fixture
def db_session(engine):
    session_factory = get_session_factory(DATABASE_URI)

    with session_factory() as db_session:
        yield db_session


def test_app_model(db_session):
    app_repo = AppRepository(session=db_session)
    app = App(name="test_app")
    app_repo.add(app, auto_commit=True)
    app2 = app_repo.get_one(name="test_app")
    assert app2 == app

    app_list = app_repo.list()
    assert app_list == [app]


def test_env_vars(db_session):
    app_repo = AppRepository(session=db_session)
    app = App(name="test_app")
    app_repo.add(app, auto_commit=True)
    assert app.env_vars == []

    var1 = EnvVar(name="var1", value="value1")
    app.env_vars.append(var1)
    app_repo.update(app, auto_commit=True)
    assert app.env_vars == [var1]
    assert var1.app == app
