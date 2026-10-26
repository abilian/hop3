# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A protected server takes changes only from an explicit selection (ADR 042, D).

The CLI reports how it chose the server (`context_source`): from `--context`
or the environment is explicit; a checkout's binding or the global current
context is not. A change also waits for the typed confirmation
(`protected_confirmed`). Read-only commands are never refused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient

from hop3 import config
from hop3.core.roles import Role
from hop3.server.asgi import create_app
from hop3.server.controllers.rpc import (
    PROTECTED_NEEDS_CONFIRMATION,
    PROTECTED_NEEDS_EXPLICIT,
    RPC_ERROR_FORBIDDEN,
)

if TYPE_CHECKING:
    from httpx import Response
    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _protected(monkeypatch):
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-rpc-protection")
    monkeypatch.setattr(config, "HOP3_UNSAFE", False)
    monkeypatch.setenv("PROTECTED", "true")


@pytest.fixture
def client(file_db: Session) -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def token(account) -> str:
    return account("ada", Role.ADMIN)


def rpc(client: TestClient, token: str, *cli_args: str, **params) -> Response:
    return client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": list(cli_args), "extra_args": {}, **params},
            "id": 7,
        },
        headers={"Authorization": f"Bearer {token}"},
    )


def kind(response: Response) -> str:
    return response.json()["error"]["data"]["kind"]


@pytest.mark.parametrize("source", ["binding", "global", None])
def test_a_change_from_a_binding_or_the_global_context_is_refused(
    client, token, source
):
    response = rpc(client, token, "app", "list", context_source=source)
    assert response.status_code == 200, "read-only commands pass"

    response = rpc(
        client,
        token,
        "env",
        "set",
        "--app",
        "x",
        "A=1",
        context_source=source,
        protected_confirmed=True,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == RPC_ERROR_FORBIDDEN
    assert kind(response) == PROTECTED_NEEDS_EXPLICIT
    assert "HOP3_CONTEXT" in response.json()["error"]["message"]


@pytest.mark.parametrize("source", ["flag", "env", "env_url"])
def test_an_explicit_change_waits_for_the_confirmation(client, token, source):
    response = rpc(
        client, token, "env", "set", "--app", "x", "A=1", context_source=source
    )
    assert kind(response) == PROTECTED_NEEDS_CONFIRMATION

    response = rpc(
        client,
        token,
        "env",
        "set",
        "--app",
        "x",
        "A=1",
        context_source=source,
        protected_confirmed=True,
    )
    # Past the protection: the command itself runs (and finds no app `x`).
    assert "protected" not in response.text


def test_an_unprotected_server_ignores_the_source(client, token, monkeypatch):
    monkeypatch.setenv("PROTECTED", "false")
    response = rpc(client, token, "env", "set", "--app", "x", "A=1")
    assert "protected" not in response.text
