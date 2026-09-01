# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Help works before the CLI has ever reached a server (ADR 036 M9.3)."""

from __future__ import annotations

import pytest
from hop3_cli.commands.help import serve_offline_help
from hop3_cli.core.suggest import read_cached_names


class FakeConfig:
    def __init__(self, *, configured: bool) -> None:
        self._configured = configured

    def is_configured(self) -> bool:
        return self._configured


def test_bare_help_is_answered_without_a_server(capsys):
    assert serve_offline_help(["help"], FakeConfig(configured=False)) is True

    out = capsys.readouterr().out
    assert "Not connected to a server yet" in out
    assert "hop3 login --ssh" in out
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


def test_a_corrupt_cache_reads_as_empty():
    """An interrupted write left NULs in a real user's cache; junk is not a command."""
    assert read_cached_names("\x00\x00\n") == []
    assert read_cached_names("app logs\n\x00\nenv set\n") == ["app logs", "env set"]
    assert read_cached_names("") == []
