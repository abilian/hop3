# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The RPC layer ships the suggestion payload to the client (ADR 036 D10)."""

from __future__ import annotations

import pytest
from litestar.testing import TestClient

from hop3.server.asgi import create_app
from hop3.server.security.tokens import create_token


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-rpc-suggestions")
    monkeypatch.setenv("HOP3_ENABLE_AUTH", "true")


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def token():
    # Authentication is checked before the command is looked up, so a
    # suggestion is only ever offered to a client that is allowed to see one.
    return create_token("testuser", scopes=["authenticated"])


def _call(client: TestClient, cli_args: list[str], token: str) -> dict:
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": cli_args, "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return response.json()


def test_unknown_command_carries_candidates(client: TestClient, token: str):
    """A typo'd command names the real ones, without the client parsing prose."""
    data = _call(client, ["cataloig"], token)["error"]["data"]

    assert data["kind"] == "unknown_command"
    assert data["typed"] == "cataloig"
    assert "catalog" in data["candidates"]


def test_unknown_command_with_no_near_match_still_carries_the_kind(
    client: TestClient, token: str
):
    data = _call(client, ["zzzzzzzz"], token)["error"]["data"]

    assert data["kind"] == "unknown_command"
    assert data["candidates"] == []


def test_positional_app_points_at_the_flag(client: TestClient, token: str):
    """`app status demo18` must be told the app is a flag (ADR 036 D5)."""
    error = _call(client, ["app", "status", "demo18"], token)["error"]

    assert error["data"]["kind"] == "unknown_argument"
    assert error["data"]["hint"] == "--app demo18"
    assert "--app demo18" in error["message"]


def test_a_plain_failure_carries_no_payload(client: TestClient, token: str):
    """Only failures with something to suggest get a payload."""
    error = _call(client, ["help"], token)
    assert "error" not in error
