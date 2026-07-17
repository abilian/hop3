# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""`hop3 app credentials` / `hop3 app admin-reset` (ADR 056)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from hop3.commands.app import CredentialsCmd
from hop3.deployers import admin_bootstrap
from hop3.deployers.admin_bootstrap import provision_admin_credential
from hop3.deployers.env_provisioning import set_env_vars
from hop3.orm import App


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    BigIntAuditBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def operator(monkeypatch):
    monkeypatch.setattr(
        admin_bootstrap, "config", SimpleNamespace(OPERATOR_EMAIL="op@example.com")
    )


def _texts(result: list[dict]) -> str:
    return " ".join(r.get("text", "") for r in result)


def _seed(session: Session, name: str) -> App:
    app = App(name=name, hostname=f"{name}.example.com", port=8000)
    session.add(app)
    session.commit()
    set_env_vars(app, {"HOST_NAME": f"{name}.example.com"}, session)
    provision_admin_credential(
        app, {"email": "operator", "password": {"generate": "password"}}, session
    )
    session.commit()
    return app


def test_credentials_shows_the_block(test_db, operator):
    _seed(test_db, "wiki")
    out = _texts(CredentialsCmd(db_session=test_db).call("--app", "wiki"))
    assert "op@example.com" in out
    assert "https://wiki.example.com/" in out
    assert "INITIAL" in out


def test_credentials_absent(test_db):
    app = App(name="plain", hostname="p.local", port=8000)
    test_db.add(app)
    test_db.commit()
    out = _texts(CredentialsCmd(db_session=test_db).call("--app", "plain"))
    assert "no Hop3-managed admin credential" in out
