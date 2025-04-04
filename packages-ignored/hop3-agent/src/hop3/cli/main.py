# Copyright (c) 2024-2025, Abilian SAS
"""Main entry point for the Hop3 CLI.

This module provides the main entry point for the Hop3 CLI. It defines
the main function that is called when the CLI is invoked from the
command line.

The main function parses command-line arguments, creates a parser (using
the argparse module), and invokes the appropriate command based on the
parsed arguments.
"""

from __future__ import annotations

import inspect
import sys
from argparse import ArgumentParser
from collections.abc import Callable
from typing import TYPE_CHECKING

from hop3.lib.scanner import scan_package
from hop3.orm import AppRepository, get_session_factory

from .help import Help, print_help
from .registry import COMMAND_REGISTRY

if TYPE_CHECKING:
    from hop3.orm import App

scan_package("hop3.cli.commands")
scan_package("hop3.plugins")


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

    sig = inspect.signature(func)
    parameters = sig.parameters
    if "_parser" in parameters:
        kwargs["_parser"] = parser

    session_factory = get_session_factory()
    with session_factory() as db_session:
        if "db_session" in parameters:
            kwargs["db_session"] = db_session

        # Special handling of the "app" argument
        # which will be converted to an App instance
        app_name = kwargs.pop("app", None)
        if app_name:
            kwargs["app"] = get_app(app_name, db_session)

        func(**kwargs)

        db_session.commit()


def get_app(app_name, db_session) -> App:
    app_repo = AppRepository(session=db_session)
    return app_repo.get_one(name=app_name)


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
    commands = sorted(COMMAND_REGISTRY.values(), key=lambda cmd: cmd.__name__)
    for cmd_class in commands:
        cmd = cmd_class()
        add_cmd_to_subparsers(subparsers, cmd)

    return parser


def add_cmd_to_subparsers(subparsers, cmd):
    # Determine the command's name
    name = getattr(cmd, "name", None)
    if not name:
        name = cmd.__class__.__name__.replace("Cmd", "").lower()

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
