# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for hop3-testing."""

from __future__ import annotations

import click

from .build import build_ready_image, build_test_image
from .catalog import list_tests, show_test
from .modes import ci, dev, nightly
from .run import run_command
from .test import apps_test, package, system_test

__all__ = [
    "apps_test",
    "build_ready_image",
    "build_test_image",
    "ci",
    "dev",
    "list_tests",
    "nightly",
    "package",
    "register_commands",
    "run_command",
    "show_test",
    "system_test",
]


def register_commands(cli: click.Group) -> None:
    """Register all commands with the CLI group."""
    cli.add_command(list_tests)
    cli.add_command(show_test)
    cli.add_command(dev)
    cli.add_command(ci)
    cli.add_command(nightly)
    cli.add_command(run_command)
    cli.add_command(package)
    cli.add_command(system_test)
    cli.add_command(apps_test)
    cli.add_command(build_ready_image)
    cli.add_command(build_test_image)
