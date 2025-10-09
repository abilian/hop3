# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import json
import traceback
from typing import TYPE_CHECKING

from starlette.responses import Response

from hop3.commands import Command
from hop3.lib.registry import lookup
from hop3.lib.scanner import scan_package
from hop3.lib.types import JsonDict
from hop3.orm import get_session_factory
from hop3.server.singletons import router

if TYPE_CHECKING:
    from starlette.requests import Request


scan_package("hop3.commands")
commands = {command.name: command for command in lookup(Command)}


# Public commands that don't require authentication
PUBLIC_COMMANDS = {"auth:login", "auth:register", "help"}

# Commands that need the authenticated username passed as first argument
USERNAME_COMMANDS = {
    "auth:whoami",
    # Admin commands (all require authenticated username for permission checks)
    "admin:user:add",
    "admin:user:remove",
    "admin:user:list",
    "admin:user:enable",
    "admin:user:disable",
    "admin:user:grant-admin",
    "admin:user:revoke-admin",
    "admin:user:set-password",
    "admin:user:info",
    "admin:user:generate-token",
}


def requires_authentication(command: str) -> bool:
    """Check if a command requires authentication.

    Args:
        command: The command name

    Returns:
        True if authentication is required, False otherwise
    """
    return command not in PUBLIC_COMMANDS


def command_needs_username(command: str) -> bool:
    """Check if a command needs the authenticated username.

    Args:
        command: The command name

    Returns:
        True if the command needs the username, False otherwise
    """
    return command in USERNAME_COMMANDS


@router.post("/rpc")
async def handle_rpc(request: Request):
    json_request = await request.json()

    method = json_request["method"]
    assert method == "cli"

    params = json_request["params"]
    cli_args = params["cli_args"]
    extra_args = params["extra_args"]

    command = cli_args[0]
    args = cli_args[1:]

    # Check authentication for commands that require it
    # Only check if AuthenticationMiddleware is installed (i.e., auth is enabled)
    if requires_authentication(command):
        # Check if user attribute is available (auth middleware installed)
        if "user" in request.scope:
            if not request.user.is_authenticated:
                error_rpc = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": 401,
                        "message": "Authentication required. Use 'hop3 auth:login' to authenticate.",
                    },
                    "id": json_request.get("id", 1),
                }
                return Response(
                    json.dumps(error_rpc),
                    media_type="application/json",
                    status_code=401,
                )

            # Pass authenticated username to commands that need it
            if command_needs_username(command):
                args = (request.user.display_name, *args)

    try:
        result = call(command, args, extra_args)
        result_rpc = {"jsonrpc": "2.0", "result": result, "id": 1}
        json_result = json.dumps(result_rpc)
        return Response(json_result, media_type="application/json")
    except ValueError as e:
        traceback.print_exc()
        # Return JSON-RPC error instead of HTTP exception
        error_rpc = {
            "jsonrpc": "2.0",
            "error": {
                "code": -32602,  # Invalid params
                "message": str(e),
            },
            "id": json_request.get("id", 1),
        }
        return Response(
            json.dumps(error_rpc),
            media_type="application/json",
            status_code=200,  # JSON-RPC errors still return 200
        )
    except Exception as e:
        traceback.print_exc()
        # Return JSON-RPC error for any exception
        error_rpc = {
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,  # Internal error
                "message": f"{type(e).__name__}: {e!s}",
            },
            "id": json_request.get("id", 1),
        }
        return Response(
            json.dumps(error_rpc),
            media_type="application/json",
            status_code=200,  # JSON-RPC errors still return 200
        )


def call(command_name: str, args: list[str], extra_args: JsonDict):
    command_class = commands.get(command_name)
    if command_class is None:
        msg = f"Command {command_name} not found"
        raise ValueError(msg)

    session_factory = get_session_factory()
    with session_factory() as db_session:
        class_args = {}

        if "db_session" in command_class.__annotations__:
            class_args = {"db_session": db_session}

        try:
            command = command_class(**class_args)
        except Exception as e:
            error_msg = f"Failed to create command: {e}"
            raise ValueError(error_msg) from e

        try:
            result = command.call(*args, **extra_args)
        except Exception as e:
            error_msg = f"Command execution failed: {e}"
            raise ValueError(error_msg) from e

        return result
