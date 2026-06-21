# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `addon expose` / `addon unexpose` commands + destroy teardown.

The expose helper is mocked; these cover the command-level argument/resolution
logic (source/host resolution, ambiguity, the source=any warning, teardown).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hop3.commands import services
from hop3.commands.services import (
    AddonDestroyCmd,
    AddonExposeCmd,
    AddonUnexposeCmd,
)


def _items_by_type(items: list) -> dict:
    out: dict = {}
    for it in items:
        out.setdefault(it["t"], []).append(it)
    return out


def _expose_cmd() -> AddonExposeCmd:
    return AddonExposeCmd(port_claim_repo=MagicMock())


# --- AddonExposeCmd -------------------------------------------------------


def test_expose_requires_source():
    with patch.object(services, "_resolve_addon_types", return_value=["postgres"]):
        # No --source, and EXPOSE_DEFAULT_SOURCE is empty in test mode.
        items = _expose_cmd().call("mydb")
    assert items[0]["t"] == "error"
    assert "--source is required" in items[0]["text"]


def test_expose_requires_host_when_no_admin_domain():
    with patch.object(services, "_resolve_addon_types", return_value=["postgres"]):
        items = _expose_cmd().call("mydb", "--source", "any")
    assert items[0]["t"] == "error"
    assert "external host" in items[0]["text"].lower()


def test_expose_ambiguous_type():
    with patch.object(
        services, "_resolve_addon_types", return_value=["postgres", "redis"]
    ):
        items = _expose_cmd().call("cache", "--source", "any", "--host", "h")
    assert items[0]["t"] == "error"
    assert "ambiguous" in items[0]["text"].lower()


def test_expose_happy_path_returns_data_and_summary():
    result = {
        "type": "postgres",
        "addon_name": "mydb",
        "host": "db.example.com",
        "public_port": 54312,
        "source": "203.0.113.0/24",
        "url": "postgresql://u:secret@db.example.com:54312/mydb",
        "already_exposed": False,
    }
    with (
        patch.object(services, "_resolve_addon_types", return_value=["postgres"]),
        patch.object(services, "expose_addon", return_value=result) as mock_expose,
    ):
        items = _expose_cmd().call(
            "mydb", "--source", "203.0.113.0/24", "--host", "db.example.com"
        )
    mock_expose.assert_called_once()
    assert mock_expose.call_args.kwargs["source"] == "203.0.113.0/24"
    assert mock_expose.call_args.kwargs["host"] == "db.example.com"
    by_type = _items_by_type(items)
    assert "data" in by_type
    assert "summary" in by_type
    assert "warning" not in by_type  # scoped source -> no internet warning


def test_expose_any_source_emits_warning():
    result = {
        "type": "postgres",
        "addon_name": "mydb",
        "host": "h",
        "public_port": 54312,
        "source": "any",
        "url": "postgresql://u:secret@h:54312/mydb",
        "already_exposed": False,
    }
    with (
        patch.object(services, "_resolve_addon_types", return_value=["postgres"]),
        patch.object(services, "expose_addon", return_value=result),
    ):
        items = _expose_cmd().call("mydb", "--source", "any", "--host", "h")
    assert "warning" in _items_by_type(items)


# --- AddonUnexposeCmd -----------------------------------------------------


def test_unexpose_not_exposed_message():
    with (
        patch.object(services, "_resolve_addon_types", return_value=["postgres"]),
        patch.object(services, "unexpose_addon", return_value=False),
    ):
        items = AddonUnexposeCmd(port_claim_repo=MagicMock()).call("mydb")
    assert items[0]["t"] == "text"
    assert "not exposed" in items[0]["text"]


def test_unexpose_success():
    with (
        patch.object(services, "_resolve_addon_types", return_value=["postgres"]),
        patch.object(services, "unexpose_addon", return_value=True) as mock_un,
    ):
        items = AddonUnexposeCmd(port_claim_repo=MagicMock()).call("mydb")
    mock_un.assert_called_once()
    assert any("Removed public exposure" in it.get("text", "") for it in items)


# --- destroy teardown -----------------------------------------------------


def test_destroy_auto_unexposes():
    addon = MagicMock()
    addon.exists.return_value = True
    cred_repo = MagicMock()
    cred_repo.list_by_addon.return_value = []
    cmd = AddonDestroyCmd(addon_credential_repo=cred_repo)

    with (
        patch.object(services, "get_addon", return_value=addon),
        patch.object(services, "unexpose_addon", return_value=True) as mock_un,
    ):
        cmd.call("mydb", "--type", "postgres")

    mock_un.assert_called_once()
    assert mock_un.call_args.args[:2] == ("postgres", "mydb")
    addon.destroy.assert_called_once()
