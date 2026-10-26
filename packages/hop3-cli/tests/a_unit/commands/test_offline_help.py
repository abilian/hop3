# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Help works before the CLI has ever reached a server (ADR 036 M9.3)."""

from __future__ import annotations

import pytest
from hop3_cli.commands.help import serve_offline_help
from hop3_cli.config import Config
from hop3_cli.core.resolution import resolve_context
from hop3_cli.core.suggest import read_cached_names
from hop3_cli.core.target import Target, resolve_target


class FakeConfig:
    def __init__(self, *, configured: bool) -> None:
        self._configured = configured

    def is_configured(self) -> bool:
        return self._configured

    def require_target(self) -> Target:
        """What a CLI with no context at all answers."""
        return resolve_target(resolve_context(None), Config(data={}))


def test_bare_help_is_answered_without_a_server(capsys):
    assert serve_offline_help(["help"], FakeConfig(configured=False)) is True

    out = capsys.readouterr().out
    assert "not connected to a server yet" in out
    assert "hop3 login <user>@<host>" in out
    for command in ("deploy", "app", "env", "context"):
        assert command in out


def test_help_for_one_command_says_where_the_detail_lives(capsys):
    serve_offline_help(["help", "deploy"], FakeConfig(configured=False))

    assert "Detailed help for `deploy`" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("args", "configured"),
    [
        (["help"], True),  # a configured CLI asks the server, as before
        (["apps"], False),  # everything else still fails loudly
        ([], False),
    ],
)
def test_not_handled_here(args, configured):
    assert serve_offline_help(args, FakeConfig(configured=configured)) is False


def test_a_configured_context_is_not_answered_offline(monkeypatch):
    """
    The help path against the real predicate, not a stand-in.

    Every test above hands `serve_offline_help` a `FakeConfig`, so none of them
    could see that `Config.is_configured` did not know where ADR 042 r2 keeps a
    context's address. `hop3 --context prod app --help` printed the built-in
    list while `hop3 --context prod system info` reached that same server.
    """
    from hop3_cli.config import Config  # ruff:ignore[import-outside-top-level]

    for var in ("HOP3_DEV_MODE", "HOP3_API_URL", "HOP3_CONTEXT"):
        monkeypatch.delenv(var, raising=False)
    config = Config(data={"contexts": {"prod": {"server": "ssh://root@prod"}}})
    config.set_context_override("prod")

    assert serve_offline_help(["help", "app"], config) is False


def test_a_corrupt_cache_reads_as_empty():
    """An interrupted write left NULs in a real user's cache; junk is not a command."""
    assert read_cached_names("\x00\x00\n") == []
    assert read_cached_names("app logs\n\x00\nenv set\n") == ["app logs", "env set"]
    assert read_cached_names("") == []
