# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`help --all --json` answers with the command tree as data (ADR 036 M9.4)."""

from __future__ import annotations

import pytest
from litestar.testing import TestClient

from hop3.server.asgi import create_app


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-help-export")


@pytest.fixture
def client():
    return TestClient(create_app())


def _help(client: TestClient, args: list[str], extra: dict) -> list[dict]:
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": args, "extra_args": extra},
            "id": 1,
        },
    )
    return response.json()["result"]


def _entries(client: TestClient) -> list[dict]:
    result = _help(client, ["help", "--all"], {"json_output": True})
    assert result[0]["t"] == "data"
    return result[0]["data"]["commands"]


def test_the_export_describes_every_command(client: TestClient):
    entries = _entries(client)
    by_name = {entry["name"]: entry for entry in entries}

    assert len(entries) > 100
    destroy = by_name["app destroy"]
    assert destroy["summary"]
    assert destroy["destructive"] is True
    assert destroy["aliases"] == ["destroy"]
    assert by_name["app"]["namespace"] is True
    assert by_name["env set"]["namespace"] is False


def test_hidden_commands_are_marked_not_dropped(client: TestClient):
    """Consumers apply their own rule; the export does not decide for them."""
    entries = _entries(client)

    assert any(entry["hidden"] for entry in entries)
    assert {"help commands"} <= {e["name"] for e in entries}


def test_without_json_help_is_still_a_page(client: TestClient):
    result = _help(client, ["help", "--all"], {})

    assert all(item["t"] != "data" for item in result)


def test_the_names_endpoint_stays_names_only(client: TestClient):
    """The completion cache reads this one; its shape must not drift."""
    result = _help(client, ["help", "commands"], {})
    names = result[0]["data"]["commands"]

    assert all(isinstance(name, str) for name in names)
    assert "help commands" not in names  # hidden commands stay out of completion
