# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for hop3-testing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .catalog import list_tests
from .test import system_test
from .upgrade_chain import upgrade_chain
from .why import why_cmd

if TYPE_CHECKING:
    import click

__all__ = [
    "list_tests",
    "register_commands",
    "system_test",
    "upgrade_chain",
    "why_cmd",
]


def register_commands(cli: click.Group) -> None:
    """
    Register all commands with the CLI group.

    The image sweep (formerly `matrix`/`cloud`) folded into `run --images`
    (ADR 052 D9), so there is no separate cloud command.
    """
    cli.add_command(system_test)  # registered under its name, "run" (ADR 052 D9)
    cli.add_command(system_test, name="system")  # deprecated alias; same command
    cli.add_command(list_tests)
    cli.add_command(why_cmd)
    cli.add_command(upgrade_chain)
