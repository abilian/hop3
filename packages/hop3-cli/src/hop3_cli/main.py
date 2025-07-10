# Copyright (c) 2024-2025, Abilian SAS
"""Simple client-side script for Hop3.

All the logic is implemented on the server side, this script is just a
thin wrapper around SSH to communicate with the server.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import requests.exceptions
from jsonrpcclient import Error, Ok
from loguru import logger

from .arguments import generate_archive
from .client import Client
from .config import Config
from .console import err
from .printer import Printer
from .types import JsonDict

logger.remove()
# TODO: enable logging to stderr when properly configured
# logger.add(sys.stderr)


def main():
    args = sys.argv[1:]
    run_command_from_args(args)


def run_command_from_args(cli_args: list[str]) -> None:
    # namespace = parse_args(args)
    #
    # if "config_file" in namespace:
    #     config = get_config(namespace.config_file)
    # else:
    #     config = Config("", {})
    # args = namespace.args

    config = get_config()
    client = Client(config=config, state=None)

    if not cli_args:
        cli_args = ["help"]

    extra_args = get_extra_args(cli_args)

    response = None
    try:
        response = client.rpc("cli", cli_args, **extra_args)
    except requests.exceptions.ConnectionError:
        err(f"Could not connect to the Hop3 server at {client.rpc_url}. Is it running?")
    except requests.exceptions.HTTPError as e:
        err(f"HTTP error while connecting to the Hop3 server:\n{e}")
    except Exception as e:
        err(f"Error while executing command:\n{e}")

    match response:
        case Ok(result=result):
            Printer().print(result)
        case Error(message=message):
            err(f"Error:\n{message}")
        case None:
            pass

    if client.tunnel:
        client.tunnel.stop()


#
# Ad-hoc functions to generate extra arguments for commands.
# TODO: refactor properly.
#
def get_extra_args(args: list[str]) -> JsonDict:
    """Generate a dictionary of extra arguments."""
    command = args[0]
    match command:
        case "deploy":
            extra_args = {
                "repository": pack_repository(),
            }
        case _:
            extra_args = {}
    return extra_args


def pack_repository() -> str:
    tar_gz = generate_archive(Path())
    return base64.b64encode(tar_gz).decode("ascii")


# TODO: dummy config, to be replaced
def get_config() -> Config:
    return Config({"host": "localhost", "port": 8000})
