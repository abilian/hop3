# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for hop3-testing tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_test_modes(tmp_path, monkeypatch):
    """Never read the developer's real ~/.hop3/test-modes.toml during tests.

    The mode-overrides file ($HOP3_TEST_MODES) lets the Test Lab edit profiles,
    but tests must see the built-in MODES, not whatever a developer happened to
    save through the UI. Point the env at a non-existent path so load_modes()
    falls back to the built-ins; tests that exercise overrides set their own
    HOP3_TEST_MODES (which, running after this, takes precedence).
    """
    monkeypatch.setenv("HOP3_TEST_MODES", str(tmp_path / "isolated-test-modes.toml"))
