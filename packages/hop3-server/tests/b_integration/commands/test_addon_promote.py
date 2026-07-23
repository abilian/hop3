# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests: per-addon env namespacing, attach/detach, and promote.

Real in-memory DB + real encryptor; the addon's ``get_connection_details`` is
mocked (no live postgres). Mirrors the fixture style of
``test_services_commands_integration.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest

from hop3.commands.services import (
    AddonAttachCmd,
    AddonDetachCmd,
    AddonPromoteCmd,
)
from hop3.orm import App, EnvVar
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    EnvVarRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

PG1 = {"DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db1", "PGHOST": "127.0.0.1"}
PG2 = {"DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db2", "PGHOST": "127.0.0.1"}


@pytest.fixture
def app_repo(db_session: Session) -> AppRepository:
    return AppRepository(session=db_session)


@pytest.fixture
def cred_repo(db_session: Session) -> AddonCredentialRepository:
    return AddonCredentialRepository(session=db_session)


@pytest.fixture
def env_repo(db_session: Session) -> EnvVarRepository:
    return EnvVarRepository(session=db_session)


@pytest.fixture
def app(db_session: Session) -> App:
    a = App(name="myapp", hostname="myapp.example.com", port=8000)
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def _attach(repos, name, conn, *, primary=False) -> list:
    app_repo, cred_repo, env_repo = repos
    cmd = AddonAttachCmd(
        app_repo=app_repo, addon_credential_repo=cred_repo, env_var_repo=env_repo
    )
    args = [name, "--app", "myapp", "--type", "postgres"]
    if primary:
        args.append("--primary")
    with patch("hop3.commands.services.get_addon") as mock_get_addon:
        addon = Mock()
        addon.get_connection_details.return_value = conn
        mock_get_addon.return_value = addon
        return cmd.call(*args)


def _detach(repos, name) -> list:
    app_repo, cred_repo, env_repo = repos
    cmd = AddonDetachCmd(
        app_repo=app_repo, addon_credential_repo=cred_repo, env_var_repo=env_repo
    )
    return cmd.call(name, "--app", "myapp", "--type", "postgres")


def _promote(repos, name) -> list:
    app_repo, cred_repo, env_repo = repos
    cmd = AddonPromoteCmd(
        app_repo=app_repo, addon_credential_repo=cred_repo, env_var_repo=env_repo
    )
    return cmd.call(name, "--app", "myapp", "--type", "postgres")


def _env(db_session, app_id, name) -> str | None:
    db_session.expire_all()
    row = db_session.query(EnvVar).filter_by(app_id=app_id, name=name).first()
    return row.value if row else None


@pytest.fixture
def repos(app_repo, cred_repo, env_repo):
    return (app_repo, cred_repo, env_repo)


@pytest.mark.integration
class TestAddonNamespacing:
    def test_first_addon_is_primary_unprefixed(self, db_session, app, repos):
        _attach(repos, "pg1", PG1)
        assert _env(db_session, app.id, "DATABASE_URL") == PG1["DATABASE_URL"]
        assert _env(db_session, app.id, "PG1_DATABASE_URL") is None

    def test_second_addon_is_secondary_prefixed(self, db_session, app, repos):
        _attach(repos, "pg1", PG1)
        _attach(repos, "pg2", PG2)
        # pg1 keeps the unprefixed vars; pg2 is prefixed.
        assert _env(db_session, app.id, "DATABASE_URL") == PG1["DATABASE_URL"]
        assert _env(db_session, app.id, "PG2_DATABASE_URL") == PG2["DATABASE_URL"]

    def test_attach_primary_flag_demotes_others(self, db_session, app, repos):
        _attach(repos, "pg1", PG1)
        _attach(repos, "pg2", PG2, primary=True)
        # pg2 is now primary (unprefixed); pg1 demoted to prefixed.
        assert _env(db_session, app.id, "DATABASE_URL") == PG2["DATABASE_URL"]
        assert _env(db_session, app.id, "PG1_DATABASE_URL") == PG1["DATABASE_URL"]
        assert _env(db_session, app.id, "PG2_DATABASE_URL") is None


@pytest.mark.integration
class TestAddonPromote:
    def test_promote_flips_primary(self, db_session, app, repos):
        _attach(repos, "pg1", PG1)
        _attach(repos, "pg2", PG2)
        _promote(repos, "pg2")
        assert _env(db_session, app.id, "DATABASE_URL") == PG2["DATABASE_URL"]
        assert _env(db_session, app.id, "PG1_DATABASE_URL") == PG1["DATABASE_URL"]
        assert (
            _env(db_session, app.id, "PG2_DATABASE_URL") is None
        )  # stale spelling gone

    def test_promote_idempotent_when_already_primary(self, db_session, app, repos):
        _attach(repos, "pg1", PG1)
        result = _promote(repos, "pg1")
        assert any("already the primary" in r.get("text", "") for r in result)
        assert _env(db_session, app.id, "DATABASE_URL") == PG1["DATABASE_URL"]

    def test_promote_not_attached_errors(self, db_session, app, repos):
        _attach(repos, "pg1", PG1)
        result = _promote(repos, "ghost")
        assert result[0]["t"] == "error"
        assert "not attached" in result[0]["text"]

    def test_promote_app_not_found(self, repos):
        app_repo, cred_repo, env_repo = repos
        cmd = AddonPromoteCmd(
            app_repo=app_repo, addon_credential_repo=cred_repo, env_var_repo=env_repo
        )
        result = cmd.call("pg1", "--app", "nope", "--type", "postgres")
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]


@pytest.mark.integration
class TestAddonDetachAutoPromote:
    def test_detach_primary_auto_promotes_oldest_sibling(self, db_session, app, repos):
        _attach(repos, "pg1", PG1)  # primary
        _attach(repos, "pg2", PG2)  # secondary
        result = _detach(repos, "pg1")
        # pg2 auto-promoted: now owns the unprefixed vars; its prefixed gone.
        assert _env(db_session, app.id, "DATABASE_URL") == PG2["DATABASE_URL"]
        assert _env(db_session, app.id, "PG2_DATABASE_URL") is None
        assert any("Auto-promoted" in r.get("text", "") for r in result)

    def test_detach_non_primary_leaves_primary_intact(self, db_session, app, repos):
        _attach(repos, "pg1", PG1)  # primary
        _attach(repos, "pg2", PG2)  # secondary
        _detach(repos, "pg2")
        assert _env(db_session, app.id, "DATABASE_URL") == PG1["DATABASE_URL"]
        assert _env(db_session, app.id, "PG2_DATABASE_URL") is None  # pg2 vars removed

    def test_detach_last_addon_removes_vars(self, db_session, app, repos):
        _attach(repos, "pg1", PG1)
        _detach(repos, "pg1")
        assert _env(db_session, app.id, "DATABASE_URL") is None
