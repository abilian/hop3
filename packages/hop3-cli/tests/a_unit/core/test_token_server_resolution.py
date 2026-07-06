# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Token store key unification + empty-env-token handling (audit 2026-06 C3/C4).

The writer (``update_context_token``) and the readers (``get_api_token``,
``is_authenticated``) must key the per-server credential store by the SAME
address — the connection URL — or a token written under one key is invisible to
the readers. And an empty ``HOP3_API_TOKEN`` must be treated as unset by both
gates, or one passes while the other sends no Authorization header.

The autouse conftest fixture isolates ``$HOP3_CONFIG_DIR`` per test, so the
store reads/writes a tmp dir.
"""

from __future__ import annotations

import pytest
from hop3_cli.config import Config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No ambient HOP3_* steering for these connection-resolution tests."""
    for var in ("HOP3_API_TOKEN", "HOP3_API_URL", "HOP3_DEV_MODE"):
        monkeypatch.delenv(var, raising=False)


def test_token_write_and_read_key_agree_with_only_api_url(monkeypatch):
    """C3: a token minted for an ``HOP3_API_URL``-only connection is readable.

    Previously the writer keyed by ``get_api_url()`` but the readers keyed only
    by active/default server, so the auto-auth token was stored under a key the
    readers never consulted — 'fails once, then works'.
    """
    monkeypatch.setenv("HOP3_API_URL", "ssh://root@host.example.com")
    cfg = Config(data={})

    assert cfg.get_api_token() is None  # nothing stored yet

    cfg.update_context_token("eyJ-minted")

    assert cfg.get_api_token() == "eyJ-minted"
    assert cfg.is_authenticated() is True


def test_empty_api_token_env_is_ignored_by_both_gates(monkeypatch):
    """C4: an empty ``HOP3_API_TOKEN`` is unset for get_api_token AND is_authenticated."""
    monkeypatch.setenv("HOP3_API_TOKEN", "")
    monkeypatch.setenv("HOP3_API_URL", "ssh://root@h")
    cfg = Config(data={})

    # Empty env token ignored; no stored token -> both gates say "no auth".
    assert cfg.get_api_token() is None
    assert cfg.is_authenticated() is False

    # A real stored token is used despite the empty env shadow (no divergence).
    cfg.update_context_token("stored-tok")
    assert cfg.get_api_token() == "stored-tok"
    assert cfg.is_authenticated() is True


def test_nonempty_api_token_env_still_wins(monkeypatch):
    """A non-empty HOP3_API_TOKEN keeps priority (explicit override)."""
    monkeypatch.setenv("HOP3_API_TOKEN", "env-tok")
    monkeypatch.setenv("HOP3_API_URL", "ssh://root@h")
    cfg = Config(data={})
    cfg.update_context_token("stored-tok")

    assert cfg.get_api_token() == "env-tok"
    assert cfg.is_authenticated() is True
