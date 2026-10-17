# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
CLI for hop3-testing.

Commands:
- hop3-test run: Deploy Hop3 and run the catalog (``system`` is a deprecated alias).
  Cloud runs and the OS-image sweep are flags on `run`: ``--provider hetzner``,
  ``--images ubuntu-24.04,debian-13`` (ADR 052 D9).
- hop3-test list: List available tests (``--show NAME`` for one test's details)
- hop3-test why: Replay a saved diagnostic bundle for a failed run
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from hop3_testing.exceptions import TestingError

from .commands import register_commands

__all__ = ["cli", "main"]


@click.group(invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """
    Hop3 Test Runner - Unified testing for Hop3.

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
    """
    Entry point for the CLI.

    The package's own errors are outcomes, not crashes: "that server is not
    labelled throwaway", "the target ran out of disk", "the deploy failed".
    Each already includes a sentence saying what to do, and burying it under
    twenty frames of click internals makes the reader hunt for the one line
    that matters. So those print as the message alone.

    Anything else keeps its traceback, because an unexpected exception is a
    bug and the frames are the report. `--verbose` brings the traceback back
    for the expected ones too, for when the question is where it was raised
    rather than what it said.
    """
    try:
        cli(obj={})
    except TestingError as e:
        if "-v" in sys.argv or "--verbose" in sys.argv:
            raise
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
