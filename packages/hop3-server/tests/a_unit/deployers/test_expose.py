# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the addon-exposure helper (rootd client + DB mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hop3.deployers import expose
from hop3.deployers.expose import (
    _rewrite_url,
    allocate_public_port,
    connection_url,
    expose_addon,
    unexpose_addon,
)
from hop3.lib import Abort
from hop3.lib.rootd import RootdError

PG_URL = "postgresql://u:secret@127.0.0.1:5432/mydb"


# --- pure helpers ---------------------------------------------------------


def test_connection_url_picks_url_key():
    assert connection_url({"PGHOST": "x", "DATABASE_URL": PG_URL}) == PG_URL
    assert connection_url({"PGHOST": "x"}) is None


def test_rewrite_url_swaps_host_and_port_keeps_credentials():
    assert (
        _rewrite_url(PG_URL, "db.example.com", 54312)
        == "postgresql://u:secret@db.example.com:54312/mydb"
    )


# --- allocate_public_port -------------------------------------------------


def test_allocate_returns_a_free_in_range_port():
    repo = MagicMock()
    repo.find_active.return_value = None
    with patch.object(expose, "_port_is_free", return_value=True):
        port = allocate_public_port(repo)
    assert expose.PORT_RANGE_LOW <= port <= expose.PORT_RANGE_HIGH


def test_allocate_skips_claimed_port():
    repo = MagicMock()
    repo.find_active.side_effect = lambda n, p="tcp": (
        MagicMock() if n == 20000 else None
    )
    with patch.object(expose, "_port_is_free", return_value=True):
        port = allocate_public_port(repo)
    assert port != 20000


def test_allocate_skips_socket_bound_port():
    repo = MagicMock()
    repo.find_active.return_value = None
    with patch.object(expose, "_port_is_free", side_effect=lambda n: n != 20000):
        port = allocate_public_port(repo)
    assert port != 20000


def test_allocate_exhausted_aborts(monkeypatch):
    repo = MagicMock()
    repo.find_active.return_value = None
    # Exhaustion is identical at any range size; scan 3 ports, not all ~12.7k
    # (each iteration hits the MagicMock repo, which is what made this slow).
    monkeypatch.setattr(expose, "PORT_RANGE_LOW", 20000)
    monkeypatch.setattr(expose, "PORT_RANGE_HIGH", 20002)
    with (
        patch.object(expose, "_port_is_free", return_value=False),
        pytest.raises(Abort),
    ):
        allocate_public_port(repo)


# --- expose_addon ---------------------------------------------------------


def _addon_returning(url: str) -> MagicMock:
    addon = MagicMock()
    addon.get_connection_details.return_value = {"DATABASE_URL": url}
    return addon


def _rootd_client(call_side):
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    client.call.side_effect = call_side
    return client


def test_expose_happy_path_opens_firewall_and_proxy():
    calls = []

    def call_side(op, args):
        calls.append((op, args))
        return {"rule_id": "r1"} if op == "firewall.add_rule" else {"unit": "u1"}

    repo = MagicMock()
    repo.find_by_addon.return_value = None
    with (
        patch.object(expose, "PortClaimRepository", return_value=repo),
        patch.object(expose, "get_addon", return_value=_addon_returning(PG_URL)),
        patch.object(expose, "allocate_public_port", return_value=54312),
        patch.object(expose, "LocalRootdClient", return_value=_rootd_client(call_side)),
    ):
        result = expose_addon(
            "postgres",
            "mydb",
            source="any",
            host="db.example.com",
            db_session=MagicMock(),
        )

    ops = [op for op, _ in calls]
    assert ops == ["firewall.add_rule", "proxy.add"]  # firewall first, then proxy
    assert calls[1][1]["target_port"] == 5432
    assert result["public_port"] == 54312
    assert result["url"] == "postgresql://u:secret@db.example.com:54312/mydb"
    assert result["already_exposed"] is False


def test_expose_is_idempotent_when_already_exposed():
    existing = MagicMock(number=9999, source="10.0.0.0/8")
    repo = MagicMock()
    repo.find_by_addon.return_value = existing
    with (
        patch.object(expose, "PortClaimRepository", return_value=repo),
        patch.object(expose, "get_addon", return_value=_addon_returning(PG_URL)),
        patch.object(expose, "allocate_public_port") as mock_alloc,
        patch.object(expose, "LocalRootdClient") as mock_client,
    ):
        result = expose_addon(
            "postgres",
            "mydb",
            source="any",
            host="db.example.com",
            db_session=MagicMock(),
        )
    mock_alloc.assert_not_called()
    mock_client.assert_not_called()
    assert result["already_exposed"] is True
    assert result["public_port"] == 9999
    assert result["url"].endswith("@db.example.com:9999/mydb")


def test_expose_rolls_back_firewall_when_proxy_fails():
    calls = []

    def call_side(op, args):
        calls.append((op, args))
        if op == "firewall.add_rule":
            return {"rule_id": "r1"}
        if op == "proxy.add":
            raise RootdError("proxy boom")  # ruff:ignore[raw-string-in-exception, raise-vanilla-args]
        return {}

    repo = MagicMock()
    repo.find_by_addon.return_value = None
    with (
        patch.object(expose, "PortClaimRepository", return_value=repo),
        patch.object(expose, "get_addon", return_value=_addon_returning(PG_URL)),
        patch.object(expose, "allocate_public_port", return_value=54312),
        patch.object(expose, "LocalRootdClient", return_value=_rootd_client(call_side)),
        pytest.raises(Abort),
    ):
        expose_addon("postgres", "mydb", source="any", host="h", db_session=MagicMock())

    # The opened firewall rule is removed on rollback.
    assert ("firewall.remove_rule", {"rule_id": "r1"}) in calls


# --- unexpose_addon -------------------------------------------------------


def test_unexpose_noop_when_not_exposed():
    repo = MagicMock()
    repo.find_by_addon.return_value = None
    with patch.object(expose, "PortClaimRepository", return_value=repo):
        assert unexpose_addon("postgres", "mydb", db_session=MagicMock()) is False


def test_unexpose_drops_claim_and_tears_down_rootd():
    claim = MagicMock(rule_id="r1", app_name="expose-postgres-mydb", proxy_unit="u1")
    repo = MagicMock()
    repo.find_by_addon.return_value = claim
    calls = []

    def call_side(op, args):
        calls.append((op, args))
        return {"rules": [{"rule_id": "r2"}]} if op == "firewall.list_rules" else {}

    db = MagicMock()
    with (
        patch.object(expose, "PortClaimRepository", return_value=repo),
        patch.object(expose, "LocalRootdClient", return_value=_rootd_client(call_side)),
    ):
        assert unexpose_addon("postgres", "mydb", db_session=db) is True

    db.delete.assert_called_once_with(claim)
    ops = [op for op, _ in calls]
    assert "proxy.remove" in ops
    # Both the stored rule and the swept rule are removed.
    removed = {a.get("rule_id") for op, a in calls if op == "firewall.remove_rule"}
    assert removed == {"r1", "r2"}
