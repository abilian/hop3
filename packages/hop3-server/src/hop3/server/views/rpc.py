# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import json
import traceback
from typing import TYPE_CHECKING

from starlette.responses import Response

from hop3 import config
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


def requires_authentication(command_class: type[Command]) -> bool:
    """Check if a command requires authentication.

    Uses the declarative `requires_auth` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if authentication is required, False otherwise
    """
    return getattr(command_class, "requires_auth", True)


def command_needs_username(command_class: type[Command]) -> bool:
    """Check if a command needs the authenticated username.

    Uses the declarative `pass_username` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if the command needs the username, False otherwise
    """
    return getattr(command_class, "pass_username", False)


def command_needs_token_info(command_class: type[Command]) -> bool:
    """Check if a command needs the full token information.

    Uses the declarative `pass_token_info` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if the command needs token info (jti, exp), False otherwise
    """
    return getattr(command_class, "pass_token_info", False)


@router.post("/rpc")
async def handle_rpc(request: Request):
    json_request = await request.json()

    method = json_request["method"]
    assert method == "cli"

    params = json_request["params"]
    cli_args = params["cli_args"]
    extra_args = params["extra_args"]

    command_name = cli_args[0]
    args = cli_args[1:]

    # Look up the command class
    command_class = commands.get(command_name)

    # For security: Check authentication BEFORE revealing if command exists
    # (for commands that would require auth if they existed)
    # This prevents information disclosure about available commands
    # Skip authentication check if HOP3_UNSAFE is true (testing mode only)
    if not config.HOP3_UNSAFE and (
        command_class is None or requires_authentication(command_class)
    ):
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

    # Now check if command actually exists (after auth check)
    if command_class is None:
        error_rpc = {
            "jsonrpc": "2.0",
            "error": {
                "code": -32601,  # Method not found
                "message": f"Command '{command_name}' not found",
            },
            "id": json_request.get("id", 1),
        }
        return Response(
            json.dumps(error_rpc),
            media_type="application/json",
            status_code=404,
        )

    # Pass authenticated username to commands that need it
    if command_needs_username(command_class):
        if "user" in request.scope and request.user.is_authenticated:
            args = (request.user.display_name, *args)

    # Pass token information to commands that need it (e.g., logout)
    if command_needs_token_info(command_class):
        if "user" in request.scope and request.user.is_authenticated:
            # Extract token from Authorization header
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                # Add token to extra_args so it can be passed to the command
                extra_args["_token"] = token

    try:
        result = call(command_name, args, extra_args)
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
