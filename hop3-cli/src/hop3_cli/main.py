# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import argparse
import logging
import sys

from .commands import Command
from .commands.apps import AppsCommand
from .commands.debug import DebugCommand
from .commands.help import HelpCommand, VersionCommand
from .config import Config, get_config
from .context import Context

logger = logging.getLogger(__name__)

COMMANDS: list[type[Command]] = [
    VersionCommand,
    DebugCommand,
    HelpCommand,
    AppsCommand,
]


def main():
    args = sys.argv[1:]
    run_command_from_args(args)


def run_command_from_args(args=None):
    parsed_args = parse_args(args)

    if config_file := getattr(parsed_args, "config_file", None):
        config = get_config(config_file)
    else:
        config = Config("", {})

    context = Context(config=config, state=None)
    parsed_args.func(parsed_args, context)


def parse_args(args) -> argparse.Namespace:
    parser = make_parser()
    args = parser.parse_args(args)
    return args


def make_parser():
    parser = argparse.ArgumentParser(description="Hop3 CLI")
    subparsers = parser.add_subparsers(help="Commands", dest="subcommand")
    subparsers.required = True
    for command_cls in COMMANDS:
        command = command_cls()
        command.setup(parser, subparsers)
    return parser
