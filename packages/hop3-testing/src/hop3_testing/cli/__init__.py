# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI for hop3-testing.

Commands:
- hop3-test run: Deploy Hop3 and run the catalog (``system`` is a deprecated alias)
- hop3-test list: List available tests (``--show NAME`` for one test's details)
- hop3-test cloud: E2E on cloud infrastructure (single image or a distro matrix)
- hop3-test why: Replay a saved diagnostic bundle for a failed run
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
