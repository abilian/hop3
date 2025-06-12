# Copyright (c) 2024-2025, Abilian SAS
"""Simple client-side script for Hop3.

All the logic is implemented on the server side, this script is just a
thin wrapper around SSH to communicate with the server.
"""

from __future__ import annotations

import sys

from jsonrpcclient import Error, Ok
from loguru import logger

from .client import Client
from .config import Config
from .console import err
from .printer import Printer

logger.remove()
logger.add(sys.stderr)


def main():
    err("Hop3 remote operator.")
    args = sys.argv[1:]
    run_command_from_args(args)


# TODO: dummy config, to be replaced
def get_config() -> Config:
    return Config({"host": "localhost", "port": 8000})


def run_command_from_args(args: list[str]) -> None:
    # namespace = parse_args(args)
    #
    # if "config_file" in namespace:
    #     config = get_config(namespace.config_file)
    # else:
    #     config = Config("", {})

    config = get_config()
    context = Client(config=config, state=None)

    # args = namespace.args

    if not args:
        args = ["help"]

    cmd = args[0]

    if cmd == "debug":
        # debug_cmd(args, context)
        return

    parsed = context.rpc("cli", args)
    match parsed:
        case Ok(result=result):
            Printer().print(result)
        case Error(message=message):
            print("Error:\n", message)
