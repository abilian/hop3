# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Every local command must be inert under `--help`.

`hop3 scaffold --help` wrote a hop3.toml into whatever directory the operator
was standing in: asking a question produced a side effect. The other local
commands were safe only by accident — they need a subcommand or a target that
`--help` does not supply, so they stop before doing anything. Scaffold was the
first with no required argument, and nothing enforced the convention.

This runs every registered handler with `--help` and asserts it touched
nothing. It is deliberately generic: the next local command someone adds is
covered without their having to remember.
"""

from __future__ import annotations

import contextlib

import pytest
from hop3_cli.commands.local import _LOCAL_HANDLERS
from hop3_cli.config import Config
from hop3_cli.ui.rich_printer import RichPrinter

#: `auth` delegates unknown subcommands back to the server rather than handling
#: them, so `auth --help` is answered by the server-side help, not here.
_DELEGATES_TO_SERVER = {"auth"}

HANDLERS = sorted(set(_LOCAL_HANDLERS) - _DELEGATES_TO_SERVER)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """A working directory and HOME nothing should touch."""
    home = tmp_path / "home"
    home.mkdir()
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(workdir)
    return workdir, home


@pytest.mark.parametrize("command", HANDLERS)
def test_help_creates_nothing(command, isolated) -> None:
    """
    `--help` must not write, anywhere.

    Checks the working directory AND the home directory: a command that dropped
    a config file in ~ would be just as surprising as one writing a hop3.toml
    into the current project.
    """
    workdir, home = isolated
    handler = _LOCAL_HANDLERS[command]

    # Exiting is a legitimate way to answer --help.
    with contextlib.suppress(SystemExit):
        handler(["--help"], Config(), RichPrinter())

    assert list(workdir.iterdir()) == [], (
        f"`hop3 {command} --help` wrote into the working directory. Asking for "
        f"help must never have a side effect — handle --help before doing "
        f"anything, as the other local commands do."
    )
    assert list(home.iterdir()) == [], f"`hop3 {command} --help` wrote into HOME."
