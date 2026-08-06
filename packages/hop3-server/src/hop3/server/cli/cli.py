# Copyright (c) 2025, Abilian SAS
"""
Main entry point for the Hop3 *server* CLI.

(For the Hop3 client CLI, see package hop3-client.)
"""

from __future__ import annotations

import inspect
import re
import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter, _SubParsersAction
from functools import partial
from typing import TYPE_CHECKING, NoReturn

from advanced_alchemy.exceptions import RepositoryError

from hop3.lib.registry import lookup
from hop3.lib.repository_errors import format_repository_error
from hop3.lib.scanner import scan_package

from . import Command
from .help import print_help, print_subcommands_help

if TYPE_CHECKING:
    from collections.abc import Callable

scan_package("hop3.server.cli")


class HopServerArgumentParser(ArgumentParser):
    """Custom ArgumentParser with better error messages."""

    def error(self, message: str) -> NoReturn:
        """Override error to provide better messages for invalid commands."""
        # Check if this is an invalid choice error
        if "invalid choice:" in message:
            # Extract the invalid command from the error message
            match = re.search(r"invalid choice: '([^']+)'", message)
            if match:
                invalid_cmd = match.group(1)
                # Get available commands
                commands = lookup(Command)
                command_names = []
                for cmd in commands:
                    name = getattr(cmd, "name", None) or cmd.__name__.lower()
                    if name:  # Filter out empty names
                        command_names.append(name)
                command_names = sorted(command_names)

                self.print_usage(sys.stderr)
                print(f"\nError: Unknown command '{invalid_cmd}'", file=sys.stderr)
                print(
                    f"\nAvailable commands: {', '.join(command_names)}", file=sys.stderr
                )
                print(
                    "\nUse 'hop3-server --help' for more information.", file=sys.stderr
                )
                self.exit(2)

        # For other errors, use default behavior
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


class CLI:
    def __call__(self, args: list[str]) -> None:
        """
        Invoke the main function with the given arguments.

        Input:
        - args (list[str]): A list of strings representing command-line arguments
          that will be passed to the main function.
        """
        main(args)


def main(argv: list[str] | None = None) -> None:
    """
    Main entry point for the command-line interface.

    Input:
    - argv: A list of command-line arguments or None. If None, defaults to sys.argv[1:].
    """
    # Parse command line arguments
    parser = create_parser()
    args = parser.parse_args(argv)

    # Prepare keyword arguments from parsed arguments
    kwargs = vars(args)
    global_verbose = kwargs.pop("verbose", False)
    global_quiet = kwargs.pop("quiet", False)

    # The function to be executed is stored in the 'func' key, this is a classic idiom
    func: Callable | None = kwargs.pop("func", None)

    if not func:
        print_help()
        return

    # Merge global verbose/quiet with command-specific verbose flags
    # This allows both "hop3-server -v cmd" and "hop3-server cmd -v" to work
    for key in list(kwargs.keys()):
        if key.startswith("verbose_") or key == "verbose":
            kwargs[key] = kwargs[key] or global_verbose
        elif key.startswith("quiet_") or key == "quiet":
            kwargs[key] = kwargs[key] or global_quiet

    # If command accepts verbose/quiet parameters but doesn't have them, add global values
    sig = inspect.signature(func)
    params = sig.parameters
    if "verbose" in params and "verbose" not in kwargs:
        kwargs["verbose"] = global_verbose
    if "quiet" in params and "quiet" not in kwargs:
        kwargs["quiet"] = global_quiet

    try:
        func(**kwargs)
    except RepositoryError as exc:
        # The RPC controller unwraps RepositoryError into a Diagnosis; the
        # git-hook CLI path must do the same so a `git push` surfaces the
        # real cause instead of advanced_alchemy's generic
        # "There was an error during data processing".
        print(format_repository_error(exc), file=sys.stderr)
        sys.exit(2)


def create_parser() -> ArgumentParser:
    """
    Create and return an argument parser for the Hop3 CLI.

    This initializes an ArgumentParser with options for verbosity and dynamically
    adds sub-command parsers based on the COMMAND_REGISTRY.

    Returns:
        ArgumentParser: A parser object configured with common and sub-command arguments.
    """
    parser = HopServerArgumentParser(description="Hop3 CLI")

    # Add flags for verbosity
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="increase output verbosity",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="decrease output verbosity",
    )

    subparsers = parser.add_subparsers()

    # Sort commands alphabetically by their class' name
    commands = lookup(Command)
    commands.sort(key=lambda cmd: cmd.__name__)
    for cmd_class in commands:
        cmd = cmd_class()
        add_cmd_to_subparsers(subparsers, cmd)

    return parser


def add_cmd_to_subparsers(
    subparsers: _SubParsersAction[HopServerArgumentParser], cmd: Command
) -> None:
    # Determine the command's name
    name = getattr(cmd, "name", None)
    if not name:
        name = cmd.__class__.__name__.lower()

    if hasattr(cmd, "run"):
        func = cmd.run
    else:
        func = partial(print_subcommands_help, name)

    # Get docstring - use only first line for the help text
    doc = cmd.__doc__ or ""
    # Get first line only (before first blank line or newline)
    help_text = doc.strip().split("\n\n")[0].split("\n")[0] if doc else ""

    # Create a subparser for the command with RawDescriptionHelpFormatter
    # This preserves the formatting of the description (docstring)
    subparser = subparsers.add_parser(
        name,
        help=help_text,
        description=doc,
        formatter_class=RawDescriptionHelpFormatter,
    )
    subparser.set_defaults(func=func)

    # Add the app argument if the command has an App parameter
    sig = inspect.signature(func)
    parameters = sig.parameters
    app_param = parameters.get("app")
    # Note: this might be fragile
    if app_param and app_param.annotation == "App":
        subparser.add_argument("app", type=str)

    # Add command-specific arguments if present
    if hasattr(cmd, "add_arguments"):
        cmd.add_arguments(subparser)


if __name__ == "__main__":
    main(sys.argv[1:])
