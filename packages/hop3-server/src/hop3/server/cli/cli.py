# Copyright (c) 2025, Abilian SAS
"""Main entry point for the Hop3 *server* CLI.

(For the Hop3 client CLI, see package hop3-client.)
"""

from __future__ import annotations

import inspect
import sys
from argparse import ArgumentParser
from collections.abc import Callable

from hop3.lib.registry import lookup
from hop3.lib.scanner import scan_package

from . import Command
from .help import Help, print_help

scan_package("hop3.server.cli")


class CLI:
    def __call__(self, args: list[str]):
        """Invoke the main function with the given arguments.

        Input:
        - args (list[str]): A list of strings representing command-line arguments
          that will be passed to the main function.
        """
        main(args)


# TODO: use pluggy to get all the plugins
# def get_cli_commands():
#     cli_commands = [hop3]
#
#     # Use pluggy to get all the plugins
#     pm = get_plugin_manager()
#     cli_commands += pm.hook.cli_commands()
#
#     return cli_commands


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the command-line interface.

    Input:
    - argv: A list of command-line arguments or None. If None, defaults to sys.argv[1:].
    """
    # Parse command line arguments
    parser = create_parser()
    args = parser.parse_args(argv)

    # Prepare keyword arguments from parsed arguments
    kwargs = vars(args)
    _verbose = kwargs.pop("verbose")
    _quiet = kwargs.pop("quiet")

    # The function to be executed is stored in the 'func' key, this is a classic idiom
    func: Callable | None = kwargs.pop("func", None)

    if not func:
        print_help()
        return

    func(**kwargs)


def create_parser() -> ArgumentParser:
    """Create and return an argument parser for the Hop3 CLI.

    This initializes an ArgumentParser with options for verbosity and dynamically
    adds sub-command parsers based on the COMMAND_REGISTRY.

    Returns:
        ArgumentParser: A parser object configured with common and sub-command arguments.
    """
    parser = ArgumentParser(description="Hop3 CLI")

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


def add_cmd_to_subparsers(subparsers, cmd):
    # Determine the command's name
    name = getattr(cmd, "name", None)
    if not name:
        name = cmd.__class__.__name__.lower()

    if hasattr(cmd, "run"):
        func = cmd.run
    else:
        func = Help(name)

    # Create a subparser for the command
    subparser = subparsers.add_parser(name, help=cmd.__doc__)
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
