# Copyright (c) 2024-2025, Abilian SAS
"""Simple client-side script for Hop3.

All the logic is implemented on the server side, this script is just a
thin wrapper around SSH to communicate with the server.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import Any

import requests.exceptions
from jsonrpcclient import Error, Ok
from loguru import logger

from .arguments import generate_archive
from .client import Client
from .config import Config, get_config
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

    config = load_config()
    client = Client(config=config, state=None)

    if not cli_args:
        cli_args = ["help"]

    # Handle --help and -h flags
    # Convert "hop --help" to "hop help"
    # Convert "hop run --help" to "hop help run"
    cli_args = handle_help_flags(cli_args)

    extra_args = get_extra_args(cli_args)

    response = None
    try:
        # Ensure extra_args contains only valid keyword arguments of correct types
        validated_extra_args: dict[str, Any] = {
            k: v for k, v in extra_args.items() if isinstance(k, str) and v is not None
        }
        response = client.rpc("cli", cli_args, **validated_extra_args)
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


def handle_help_flags(args: list[str]) -> list[str]:
    """Convert --help/-h flags to help command invocations.

    Examples:
        ["--help"] -> ["help"]
        ["-h"] -> ["help"]
        ["run", "--help"] -> ["help", "run"]
        ["run", "-h"] -> ["help", "run"]
        ["run", "myapp", "--help"] -> ["help", "run"]  # help for run, not run with --help

    Args:
        args: Command-line arguments

    Returns:
        Modified arguments with --help converted to help command
    """
    if not args:
        return args

    # Check if --help or -h is anywhere in the args
    if "--help" in args or "-h" in args:
        # Remove --help and -h from args
        filtered_args = [arg for arg in args if arg not in {"--help", "-h"}]

        if not filtered_args:
            # Just "--help" with no command -> show general help
            return ["help"]
        else:
            # "command --help" -> "help command"
            # Only use the first argument as the command name
            return ["help", filtered_args[0]]

    return args


#
# Ad-hoc functions to generate extra arguments for commands.
# TODO: refactor properly.
#
def get_extra_args(args: list[str]) -> JsonDict:
    """Generate a dictionary of extra arguments."""
    command = args[0]
    match command:
        case "deploy":
            # args[0]="deploy", args[1]=app_name, args[2]=directory
            directory = Path(args[2]) if len(args) > 2 else Path()
            return {
                "repository": pack_repository(directory),
            }
        case _:
            return {}


def pack_repository(directory: Path = Path()) -> str:
    tar_gz = generate_archive(directory)
    return base64.b64encode(tar_gz).decode("ascii")


def load_config() -> Config:
    """Load configuration from the standard user location."""
    return get_config()
