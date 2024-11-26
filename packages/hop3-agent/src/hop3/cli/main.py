# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

import sys
from argparse import ArgumentParser
from collections.abc import Callable
from importlib.metadata import version

from hop3.core.app import App
from hop3.util.console import bold

from . import apps, config, git, misc, setup
from .base import COMMAND_REGISTRY

assert apps
assert config
assert git
assert setup
assert misc


class CLI:
    def __call__(self, args: list[str]):
        main(args)


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    # Parse command line arguments
    parser = create_parser()
    args = parser.parse_args(argv)

    # Run the command
    kwargs = vars(args)
    _verbose = kwargs.pop("verbose")
    _quiet = kwargs.pop("quiet")
    func: Callable | None = kwargs.pop("func", None)

    if not func:
        print_help()
        return

    app = kwargs.pop("app", None)
    if app:
        kwargs["app"] = App(app)

    func(**kwargs)


def print_help():
    package_version = version("hop3-agent")

    output = [
        "CLI to interact with Hop3",
        "",
        bold("VERSION"),
        f"  {package_version}",
        "",
        bold("USAGE"),
        "  $ hop [COMMAND]",
        "",
        bold("COMMANDS"),
    ]

    for command in sorted(COMMAND_REGISTRY.values(), key=lambda cmd: cmd.__name__):
        name = getattr(command, "name", None)
        if not name:
            name = command.__name__.replace("Cmd", "").lower()
        help_text = command.__doc__ or ""
        if "INTERNAL" in help_text:
            continue
        output.append(f"  {name:<15} {help_text}")

    print("\n".join(output))


def create_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Hop3 CLI")

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

    commands = sorted(COMMAND_REGISTRY.values(), key=lambda cmd: cmd.__name__)
    for cmd_class in commands:
        cmd = cmd_class()
        name = getattr(cmd, "name", None)
        if not name:
            name = cmd.__class__.__name__.replace("Cmd", "").lower()
        add_help = not getattr(cmd, "hide", False)
        subparser = subparsers.add_parser(name, help=cmd.__doc__, add_help=add_help)
        subparser.set_defaults(func=cmd.run)
        if hasattr(cmd, "add_arguments"):
            cmd.add_arguments(subparser)

    return parser


if __name__ == "__main__":
    main(sys.argv[1:])
