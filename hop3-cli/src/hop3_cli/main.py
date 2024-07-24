# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import argparse
import logging
import sys

from devtools import debug

from .commands import Command
from .commands.debug import DebugCommand
from .commands.help import VersionCommand
from .config import get_config

logger = logging.getLogger(__name__)

COMMANDS: list[type[Command]] = [
    VersionCommand,
    DebugCommand,
]


def main():
    args = sys.argv[1:]
    run_command_from_args(args)


def run_command_from_args(args=None, **extra):
    parsed_args = parse_args(args)

    if config_file := getattr(parsed_args, "config_file", None):
        config = get_config(config_file)
    else:
        config = None

    if config is None:
        parsed_args.func(parsed_args, **extra)
    else:
        parsed_args.func(parsed_args, config, **extra)


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
