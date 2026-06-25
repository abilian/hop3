# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Shared test fixtures for hop3-testlab."""

from __future__ import annotations

import pytest

from hop3_testlab.db import get_session_factory


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point every test at a throwaway result DB (never the real ~/.hop3 one).

    The dashboard reads the shared store, so without this a test would create /
    read the developer's ~/.hop3/test-results.db. Each test gets its own tmp DB
    and the per-path session-factory cache is cleared around it.
    """
    monkeypatch.setenv("TESTLAB_DB_PATH", str(tmp_path / "test-results.db"))
    # Per-app-instance data (keys, source clones, worktrees, artifacts) -> tmp, so
    # tests never touch the developer's ~/.hop3/testlab.
    monkeypatch.setenv("TESTLAB_DATA_DIR", str(tmp_path / "data"))
    # Bypass the auth guard by default (the auth tests opt back in). Mirrors
    # hop3-server's HOP3_UNSAFE test bypass.
    monkeypatch.setenv("TESTLAB_UNSAFE", "true")
    # Tests run over the plain-HTTP TestClient, so cookies must not be Secure.
    # Dev mode (DEBUG) gates that off — the auth/csrf tests turn UNSAFE off but
    # still need cookies to round-trip over http.
    monkeypatch.setenv("TESTLAB_DEBUG", "true")
    # Isolate config discovery from the developer's ~/.hop3/testlab/config.toml
    # (a non-existent path -> empty config -> defaults). Tests that want config
    # pass an explicit path or set the relevant env vars.
    monkeypatch.setenv("TESTLAB_CONFIG", str(tmp_path / "no-config.toml"))
    # The dashboard + profiles views read the engine's mode-overrides file
    # ($HOP3_TEST_MODES); isolate it so tests never see the developer's real
    # ~/.hop3/test-modes.toml. Tests that exercise overrides set their own.
    monkeypatch.setenv("HOP3_TEST_MODES", str(tmp_path / "isolated-test-modes.toml"))
    get_session_factory.cache_clear()
    yield
    get_session_factory.cache_clear()
