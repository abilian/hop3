# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for proxy startup reconciliation (mocked proxy helper)."""

from __future__ import annotations

from unittest.mock import ANY, patch

import pytest
from hop3_rootd import reconcile as rec
from hop3_rootd.proxy import ProxyError, ProxyUnavailableError
from hop3_rootd.state import State, StoredProxy


def _sp(addon_type: str, addon_name: str) -> StoredProxy:
    unit = f"hop3-expose-{addon_type}-{addon_name}"
    return StoredProxy(addon_type, addon_name, unit, 54000, 5432, "any", "t")


def test_reconcile_reasserts_stored_and_removes_orphan():
    state = State(proxies=[_sp("postgres", "mydb")])
    with (
        patch.object(rec.px, "add_proxy") as mock_add,
        patch.object(
            rec.px,
            "list_units",
            return_value=["hop3-expose-postgres-mydb", "hop3-expose-redis-orphan"],
        ),
        patch.object(rec.px, "remove_proxy") as mock_rm,
    ):
        report = rec.reconcile_proxies(state)

    mock_add.assert_called_once_with("postgres", "mydb", 54000, 5432, exec=ANY)
    mock_rm.assert_called_once_with(
        "hop3-expose-redis-orphan", exec=ANY
    )  # stored one untouched
    assert report.reasserted == 1
    assert report.orphans_removed == 1
    assert report.failed == 0


def test_reconcile_per_unit_failure_is_counted_not_fatal():
    state = State(proxies=[_sp("postgres", "mydb")])
    with (
        patch.object(rec.px, "add_proxy", side_effect=ProxyError("boom")),
        patch.object(rec.px, "list_units", return_value=[]),
    ):
        report = rec.reconcile_proxies(state)
    assert report.failed == 1
    assert report.reasserted == 0


def test_reconcile_unavailable_systemd_propagates():
    state = State(proxies=[_sp("postgres", "mydb")])
    with (
        patch.object(
            rec.px, "add_proxy", side_effect=ProxyUnavailableError("no systemd")
        ),
        patch.object(rec.px, "list_units", return_value=[]),
        pytest.raises(ProxyUnavailableError),
    ):
        rec.reconcile_proxies(state)
