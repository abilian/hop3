# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The environment names a target too, so it gets a name: `env`.

`HOP3_API_URL` (and `HOP3_DEV_MODE`'s localhost) are consulted by `get_api_url`
before any stored context, which made an exported variable a second, invisible
resolution system: `hop3 context` did not list it, and every place that had to
mention the current target grew a special case for it. It is a context now, and
the special cases are gone.
"""

from __future__ import annotations

import pytest
from hop3_cli.config import DEFAULT_CONTEXT_NAME, ENV_CONTEXT_NAME, Config
from hop3_cli.ui.messages import show_unauthenticated_message

ENV_URL = "https://from-env.example.com"
STORED = "https://stored.example.com"


@pytest.fixture(autouse=True)
def _no_ambient_env(monkeypatch):
    for name in ("HOP3_API_URL", "HOP3_CONTEXT", "HOP3_DEV_MODE", "HOP3_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def stored_config() -> Config:
    return Config(
        data={
            "contexts": {DEFAULT_CONTEXT_NAME: {"server": STORED}},
            "cli": {"default_context": DEFAULT_CONTEXT_NAME},
        }
    )


class TestItIsANamedContext:
    def test_the_current_context_is_env(self, monkeypatch):
        monkeypatch.setenv("HOP3_API_URL", ENV_URL)
        assert stored_config().get_current_context_name() == ENV_CONTEXT_NAME

    def test_it_is_listed(self, monkeypatch):
        monkeypatch.setenv("HOP3_API_URL", ENV_URL)
        listed = stored_config().list_global_contexts()
        assert listed[ENV_CONTEXT_NAME] == ENV_URL
        assert listed[DEFAULT_CONTEXT_NAME] == STORED, "stored ones still listed"

    def test_it_resolves_by_name(self, monkeypatch):
        monkeypatch.setenv("HOP3_API_URL", ENV_URL)
        assert Config(data={}).get_context_server(ENV_CONTEXT_NAME) == ENV_URL

    def test_dev_mode_names_the_same_context(self, monkeypatch):
        monkeypatch.setenv("HOP3_DEV_MODE", "true")
        config = Config(data={})
        assert config.get_current_context_name() == ENV_CONTEXT_NAME
        assert config.env_context_server() == "http://localhost:8000"

    def test_absent_when_nothing_is_exported(self):
        config = stored_config()
        assert config.env_context_server() is None
        assert config.get_current_context_name() == DEFAULT_CONTEXT_NAME
        assert ENV_CONTEXT_NAME not in config.list_global_contexts()


class TestNamingPrecedence:
    """An explicitly chosen name still wins; the guard handles a real conflict."""

    def test_an_explicit_context_keeps_its_own_name(self, monkeypatch):
        monkeypatch.setenv("HOP3_API_URL", ENV_URL)
        config = stored_config()
        config._context_override = "prod"
        assert config.get_current_context_name() == "prod"

    def test_hop3_context_keeps_its_own_name(self, monkeypatch):
        monkeypatch.setenv("HOP3_API_URL", ENV_URL)
        monkeypatch.setenv("HOP3_CONTEXT", "prod")
        assert stored_config().get_current_context_name() == "prod"

    def test_env_outranks_the_stored_default(self, monkeypatch):
        """It must, because `get_api_url` connects there."""
        monkeypatch.setenv("HOP3_API_URL", ENV_URL)
        config = stored_config()
        assert config.get_api_url() == ENV_URL
        assert config.get_current_context_name() == ENV_CONTEXT_NAME


class TestTheAuthFailureNamesTheTarget:
    def test_it_names_the_server_and_context(self, capsys):
        config = stored_config()
        config.set_active_server(STORED)
        show_unauthenticated_message(config)
        out = capsys.readouterr().err
        assert STORED in out
        assert f"context {DEFAULT_CONTEXT_NAME!r}" in out

    def test_it_teaches_the_current_sign_in_command(self, capsys):
        show_unauthenticated_message(stored_config())
        out = capsys.readouterr().err
        assert "hop3 login root@your-server.com" in out
        # It used to advertise `hop3 init`, which the CLI's own help retired,
        # and claim the token lands in config.toml, which stopped being true
        # when tokens moved to the credential store.
        assert "hop3 init" not in out
        assert "config.toml" not in out

    def test_an_env_target_is_told_what_actually_fixes_it(self, capsys, monkeypatch):
        """
        `hop3 login` would store a credential for whatever it resolves, while
        every command keeps going to the exported URL. Advertising it here would
        send the operator round a loop.
        """
        monkeypatch.setenv("HOP3_API_URL", ENV_URL)
        show_unauthenticated_message(stored_config())
        out = capsys.readouterr().err
        assert ENV_URL in out
        assert "HOP3_API_TOKEN" in out
        assert "unset HOP3_API_URL" in out
        assert "hop3 login root@" not in out

    def test_no_target_falls_back_to_the_generic_line(self, capsys):
        """A configured CLI with nothing selected still gets an answer."""
        show_unauthenticated_message(Config(data={}))
        assert "Authentication required" in capsys.readouterr().err
