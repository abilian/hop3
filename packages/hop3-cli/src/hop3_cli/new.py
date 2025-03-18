# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings

from devtools import debug
from jsonrpcclient import Error, Ok
from urllib3.exceptions import InsecureRequestWarning

from .config import Config, get_config
from .context import Context
from .printer import Printer

warnings.filterwarnings("ignore", category=InsecureRequestWarning)
logger = logging.getLogger(__name__)


def main() -> None:
    args = sys.argv[1:]
    run_command_from_args(args)


def run_command_from_args(args=None) -> None:
    namespace = parse_args(args)

    if "config_file" in namespace:
        config = get_config(namespace.config_file)
    else:
        config = Config("", {})

    context = Context(config=config, state=None)
    args = namespace.args

    if not args:
        args = ["help"]

    if args[0] == "debug":
        debug_cmd(args, context)
        return

    parsed = context.rpc("cli", args)
    match parsed:
        case Ok(result=result):
            Printer().print(result)
        case Error(message=message):
            print("Error:\n", message)


def parse_args(args) -> argparse.Namespace:
    parser = make_parser()
    return parser.parse_args(args)


def make_parser():
    parser = argparse.ArgumentParser(description="Hop3 CLI")
    parser.add_argument(
        "--config-file",
        help="Path to the configuration file",
        default=None,
    )
    parser.add_argument(
        "args",
        default=[],
        nargs=argparse.REMAINDER,
    )
    return parser


def debug_cmd(args, context) -> None:
    config = context.config
    env = dict(sorted([(k, v) for k, v in os.environ.items() if k.startswith("HOP3_")]))
    debug(
        args,
        env,
        dict(sorted(config.data.items())),
    )
