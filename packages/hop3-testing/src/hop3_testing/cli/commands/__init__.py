# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for hop3-testing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .catalog import list_tests
from .cloud import cloud_test
from .test import system_test
from .why import why_cmd

if TYPE_CHECKING:
    import click

__all__ = [
    "cloud_test",
    "list_tests",
    "register_commands",
    "system_test",
    "why_cmd",
]


def register_commands(cli: click.Group) -> None:
    """Register all commands with the CLI group."""
    cli.add_command(system_test)
    cli.add_command(list_tests)
    cli.add_command(cloud_test)
    cli.add_command(why_cmd)
