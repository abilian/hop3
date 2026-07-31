# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`hop3 catalog refresh` output: an up-to-date catalog is not a failure.

Regression: refreshing when the source had not re-published printed
"ERROR: Catalog refresh failed: ..." — dramatic wording for the routine case of
there being nothing new, which reads as though the server rejected an attack.
"""

from __future__ import annotations

import pytest

from hop3.commands.catalog import CatalogRefreshCmd
from hop3.server.catalog.sync import CatalogInstallResult, CatalogSyncError


@pytest.fixture
def refresh_returning(monkeypatch):
    """Drive the command with a stubbed refresh outcome."""

    def _install(result):
        monkeypatch.setattr(
            "hop3.commands.catalog.refresh_catalog", lambda: result, raising=True
        )
        return CatalogRefreshCmd().call()

    return _install


def test_unchanged_catalog_is_plain_output(refresh_returning):
    """No error type, no 'failed' — just says it is current."""
    out = refresh_returning(CatalogInstallResult(serial=1785177004, changed=False))

    assert len(out) == 1
    assert out[0]["t"] != "error"
    message = out[0]["text"]
    assert "up to date" in message
    assert "1785177004" in message
    assert "failed" not in message.lower()
    assert "error" not in message.lower()


def test_updated_catalog_reports_the_new_serial(refresh_returning):
    out = refresh_returning(CatalogInstallResult(serial=42, changed=True))

    assert out[0]["t"] != "error"
    assert "refreshed to serial 42" in out[0]["text"]


def test_a_real_failure_is_still_an_error(monkeypatch):
    """A genuine rollback / fetch failure must stay loud."""

    def _boom():
        msg = "serial 1 is older than the installed serial 9 (rollback)"
        raise CatalogSyncError(msg)

    monkeypatch.setattr("hop3.commands.catalog.refresh_catalog", _boom, raising=True)

    out = CatalogRefreshCmd().call()

    assert out[0]["t"] == "error"
    assert "rollback" in out[0]["text"]
