# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

import inspect
import sys
from argparse import ArgumentParser
from collections.abc import Callable

from hop3.cli.help import print_help
from hop3.core.app import App

from . import apps, config, git, help, misc, setup
from .base import COMMAND_REGISTRY

assert apps
assert config
assert git
assert setup
assert misc
assert help


class CLI:
    def __call__(self, args: list[str]):
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

    # Special handling of the "app" argument which is converted to an App instance
    app = kwargs.pop("app", None)
    if app:
        kwargs["app"] = App(app)

    func(**kwargs)


def create_parser() -> ArgumentParser:
    """
    Create and return an argument parser for the Hop3 CLI.

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

        # Determine the command's name
        name = getattr(cmd, "name", None)
        if not name:
            name = cmd.__class__.__name__.replace("Cmd", "").lower()

        # Create a subparser for the command
        subparser = subparsers.add_parser(name, help=cmd.__doc__)
        subparser.set_defaults(func=cmd.run)

        # Add command-specific arguments if present
        if hasattr(cmd, "add_arguments"):
            cmd.add_arguments(subparser)

    return parser


if __name__ == "__main__":
    main(sys.argv[1:])
