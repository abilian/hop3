# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The destroy warning must name the server, and must appear at all.

It printed `⚠ Acting in context 'default'` — a name every single-server install
shares, so it answered the wrong question. And it printed nothing whatsoever
after `hop3 login --context prod`, because `get_current_context_name` never read
`[cli].default_context`, the key a login actually writes. So the one line that
tells an operator which machine they are about to destroy an app on was either
uninformative or absent.
"""

from __future__ import annotations

import pytest
from hop3_cli.commands.destructive import _maybe_show_context_warning
from hop3_cli.config import ENV_CONTEXT_NAME, Config
from hop3_cli.core.resolution import ContextSource
from hop3_cli.core.target import Target


@pytest.fixture(autouse=True)
def _no_ambient_env(monkeypatch):
    """The env vars under test must not leak in from the developer's shell."""
    monkeypatch.delenv("HOP3_API_URL", raising=False)
    monkeypatch.delenv("HOP3_CONTEXT", raising=False)
    monkeypatch.delenv("HOP3_DEV_MODE", raising=False)


def warn(config: Config, capsys) -> str:
    _maybe_show_context_warning(config)
    return capsys.readouterr().err


def test_names_the_address_of_a_named_context(capsys):
    config = Config(data={"cli": {"default_context": "prod"}})
    config.set_active_server("https://prod.example.com")
    out = warn(config, capsys)
    assert "https://prod.example.com" in out
    assert "context 'prod'" in out


def test_a_default_context_login_is_no_longer_silent(capsys):
    """
    The regression: `[cli].default_context` was never read.

    The context name is deliberately nothing like the hostname — asserting on
    "prod" alone would pass on the address, with the reader still broken.
    """
    config = Config(data={"cli": {"default_context": "live-eu"}})
    config.set_active_server("https://prod.example.com")
    assert "context 'live-eu'" in warn(config, capsys)


def test_an_env_override_is_named_as_the_env_context(capsys, monkeypatch):
    """
    `HOP3_API_URL` beats every context, so naming the stored one would lie.

    It needs no special case here: it is the context called `env`, and the
    generic line names it. That is the point of giving it a name.
    """
    monkeypatch.setenv("HOP3_API_URL", "https://elsewhere.example.com")
    config = Config(data={"cli": {"default_context": "prod"}})
    config.set_target(
        Target(
            ENV_CONTEXT_NAME,
            "https://elsewhere.example.com",
            None,
            ContextSource.ENV_URL,
        )
    )
    out = warn(config, capsys)
    assert "https://elsewhere.example.com" in out
    assert f"context {ENV_CONTEXT_NAME!r}" in out
    assert "prod" not in out


def test_silent_when_there_is_no_target(capsys):
    assert warn(Config(data={}), capsys) == ""


def test_silent_without_a_config(capsys):
    _maybe_show_context_warning(None)
    assert capsys.readouterr().err == ""


def test_explicit_context_flag_wins(capsys):
    config = Config(data={"cli": {"default_context": "prod"}})
    config._context_override = "staging"
    config.set_active_server("https://staging.example.com")
    out = warn(config, capsys)
    assert "context 'staging'" in out
