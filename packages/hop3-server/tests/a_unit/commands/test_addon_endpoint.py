# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the type-agnostic `addon endpoint <name>` command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hop3.commands.services import AddonEndpointCmd

_PG_URL = "postgresql://u:secret@127.0.0.1:5432/mydb"


def _data_item(result: list[dict]) -> dict | None:
    for item in result:
        if item["t"] == "data":
            return item["data"]
    return None


@patch("hop3.commands.services.get_addon")
@patch("hop3.commands.services.list_addon_instances")
def test_endpoint_resolves_type_and_returns_structured_data(mock_list, mock_get):
    mock_list.return_value = [("postgres", "mydb"), ("redis", "cache")]
    addon = MagicMock()
    addon.get_connection_details.return_value = {
        "DATABASE_URL": _PG_URL,
        "PGHOST": "127.0.0.1",
        "PGPORT": "5432",
    }
    mock_get.return_value = addon

    result = AddonEndpointCmd().call("mydb")

    mock_get.assert_called_once_with("postgres", "mydb")
    assert _data_item(result) == {
        "type": "postgres",
        "host": "127.0.0.1",
        "port": 5432,
        "url": _PG_URL,
    }


@patch("hop3.commands.services.list_addon_instances")
def test_endpoint_unknown_name_is_an_error(mock_list):
    mock_list.return_value = [("postgres", "other")]
    result = AddonEndpointCmd().call("missing")
    assert result[0]["t"] == "error"
    assert "missing" in result[0]["text"]


@patch("hop3.commands.services.list_addon_instances")
def test_endpoint_ambiguous_name_is_an_error(mock_list):
    # Same name across two types -> refuse to guess.
    mock_list.return_value = [("postgres", "cache"), ("redis", "cache")]
    result = AddonEndpointCmd().call("cache")
    assert result[0]["t"] == "error"
    assert "ambiguous" in result[0]["text"].lower()


def test_endpoint_without_name_shows_usage():
    result = AddonEndpointCmd().call()
    assert result[0]["t"] == "text"
    assert "Usage" in result[0]["text"]
