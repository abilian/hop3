# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

import sys
from argparse import ArgumentParser, HelpFormatter
from collections.abc import Callable

from hop3.core.app import App

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
        parser.print_help()
        return

    app = kwargs.pop("app", None)
    if app:
        kwargs["app"] = App(app)

    func(**kwargs)


class MyHelpFormatter(HelpFormatter):
    pass
    # def _format_usage(self, usage, actions, groups, prefix):
    #     for action in actions:
    #         if isinstance(action, _SubParsersAction):
    #             choices = {k: v for k, v in action.choices.items() if v.description}
    #             action.choices = choices
    #     return super()._format_usage(usage, actions, groups, prefix)


def create_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Hop3 CLI", formatter_class=MyHelpFormatter)

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
