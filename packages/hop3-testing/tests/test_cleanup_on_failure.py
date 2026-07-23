# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Regression: cleanup must destroy the app even after a FAILED deploy.

A partial deploy can create the app and provision some addons (e.g. postgres
before redis failed). If cleanup skipped those, every failed deploy would leak
an app dir + addon slots — the slow cause of disk and Redis-db exhaustion.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

from hop3_testing.apps.deployment import DeploymentSession
from hop3_testing.exceptions import CleanupError


def _session(*, deployed: bool) -> DeploymentSession:
    s = object.__new__(DeploymentSession)  # bypass heavy __init__
    s.app_name = "app-1"
    s.deployed = deployed
    s.console = MagicMock()
    s._preparation = MagicMock()
    return s


def test_cleanup_destroys_even_when_deploy_failed():
    s = _session(deployed=False)  # a failed deploy never set deployed=True
    with patch.object(DeploymentSession, "_destroy_app") as destroy:
        s.cleanup()
    destroy.assert_called_once()  # the partial app is still torn down
    cast("Any", s._preparation.cleanup).assert_called_once()


def test_cleanup_destroys_on_success_too():
    s = _session(deployed=True)
    with patch.object(DeploymentSession, "_destroy_app") as destroy:
        s.cleanup()
    destroy.assert_called_once()


def test_cleanup_warns_but_does_not_raise_on_destroy_error():
    s = _session(deployed=False)
    with patch.object(
        DeploymentSession, "_destroy_app", side_effect=CleanupError("boom")
    ):
        s.cleanup()  # must not raise
    cast("Any", s.console.warning).assert_called_once()
    cast("Any", s._preparation.cleanup).assert_called_once()  # temp dir still cleaned
