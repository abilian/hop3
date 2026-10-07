# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The dispatcher refuses a call the caller's role does not allow (ADR 061 §3).

Every case goes through the real HTTP stack with a real account in the
database, because the property under test is that the role is read from the
database on each call: a token carries a name, never an authority.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient

from hop3 import config
from hop3.core.roles import Role
from hop3.orm import User
from hop3.server.asgi import create_app
from hop3.server.controllers.rpc import RPC_ERROR_FORBIDDEN
from hop3.server.security.tokens import create_token

if TYPE_CHECKING:
    from httpx import Response
    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _real_auth(monkeypatch):
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-rpc-authorization")
    # Other suites turn the auth bypass on; nothing here may run with it.
    monkeypatch.setattr(config, "HOP3_UNSAFE", False)


@pytest.fixture
def client(file_db: Session) -> TestClient:
    return TestClient(create_app())


def rpc(client: TestClient, token: str | None, *cli_args: str) -> Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": list(cli_args), "extra_args": {}},
            "id": 7,
        },
        headers=headers,
    )


def test_a_viewer_reads_app_state(client, account):
    response = rpc(client, account("vera", Role.VIEWER), "app", "list")

    assert response.status_code == 200
    assert "result" in response.json()


def test_a_viewer_is_refused_a_command_that_shows_secrets(client, account):
    response = rpc(client, account("vera", Role.VIEWER), "env", "show", "--app", "x")

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == RPC_ERROR_FORBIDDEN
    assert error["data"] == {
        "kind": "forbidden",
        "command": "env show",
        "required_role": "deployer",
        "role": "viewer",
        "hint": "An admin can grant it: hop3 user set-role vera deployer",
    }
    assert response.json()["id"] == 7


def test_a_member_runs_no_command_but_whoami(client, account):
    token = account("mia", Role.MEMBER)

    assert rpc(client, token, "app", "list").status_code == 403
    assert rpc(client, token, "auth", "whoami").status_code == 200


def test_a_deployer_is_refused_user_management(client, account):
    response = rpc(client, account("dora", Role.DEPLOYER), "user", "list")

    assert response.status_code == 403
    assert response.json()["error"]["data"]["required_role"] == "admin"


def test_an_admin_manages_users(client, account):
    response = rpc(client, account("ada", Role.ADMIN), "user", "list")

    assert response.status_code == 200
    assert "ada" in response.text


def test_a_token_for_an_account_that_does_not_exist_is_refused(client, file_db):
    """However it was signed: the harnesses used to mint exactly this."""
    token = create_token("ghost", scopes=["authenticated", "admin"])

    response = rpc(client, token, "app", "list")

    assert response.status_code == 401
    assert "which does not exist" in response.json()["error"]["message"]
    assert response.json()["error"]["data"]["kind"] == "account_unusable"


def test_a_disabled_account_is_refused(client, account):
    token = account("dan", Role.ADMIN, active=False)

    response = rpc(client, token, "app", "list")

    assert response.status_code == 401
    assert "which is disabled" in response.json()["error"]["message"]
    assert response.json()["error"]["data"]["kind"] == "account_unusable"


def test_a_demotion_takes_effect_on_the_next_call(client, account, file_db):
    """No token is revoked: the role is read again on every call."""
    token = account("dora", Role.DEPLOYER)
    assert rpc(client, token, "app", "list").status_code == 200

    user = file_db.query(User).filter_by(username="dora").one()
    user.role = Role.MEMBER
    file_db.commit()

    assert rpc(client, token, "app", "list").status_code == 403


def test_public_commands_need_no_account(client):
    assert rpc(client, None, "help").status_code == 200


def test_a_member_gets_no_token(client, account):
    account("mia", Role.MEMBER)

    response = rpc(client, None, "auth", "get-token", "mia", "password123")

    result = response.json()["result"]
    assert result[0]["t"] == "error"
    assert "is a member" in result[0]["text"]
