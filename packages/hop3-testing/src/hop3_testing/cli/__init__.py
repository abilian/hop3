# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI for hop3-testing.

This module provides the new CLI commands:
- hop3-test list: List available tests
- hop3-test show: Show test details
- hop3-test dev: Run developer tests
- hop3-test ci: Run CI tests
- hop3-test package: Validate a package

The original functionality is preserved and can be accessed via:
- hop3-test run: Run tests (original behavior)
"""

from __future__ import annotations

from pathlib import Path

import click

from .commands import register_commands

__all__ = ["cli", "main"]


@click.group(invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Hop3 Test Runner - Unified testing for Hop3.

    Run deployment tests, demos, and tutorials against Hop3 targets.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["root"] = Path.cwd()

    # If no subcommand, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Register all commands
register_commands(cli)


def main() -> None:
    """Entry point for the CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
