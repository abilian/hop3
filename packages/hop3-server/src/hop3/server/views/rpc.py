# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import json
import traceback
from typing import TYPE_CHECKING

from devtools import debug
from starlette.exceptions import HTTPException
from starlette.responses import Response

from hop3.commands import Command
from hop3.lib.registry import lookup
from hop3.lib.scanner import scan_package
from hop3.orm import get_session_factory

if TYPE_CHECKING:
    from starlette.requests import Request

    from hop3.server.asgi import SetupContext

scan_package("hop3.commands")
commands = {command.name: command for command in lookup(Command)}


async def handle_rpc(request: Request):
    json_request = await request.json()

    method = json_request["method"]
    assert method == "cli"

    params = json_request["params"][0]
    command = params[0]
    args = params[1:]

    try:
        result = call(command, args)
        result_rpc = {"jsonrpc": "2.0", "result": result, "id": 1}
        json_result = json.dumps(result_rpc)
        return Response(json_result, media_type="application/json")
    except ValueError as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


def call(command_name: str, args: list[str]):
    debug(command_name, args)
    command_class = commands.get(command_name)
    if command_class is None:
        msg = f"Command {command_name} not found"
        raise ValueError(msg)

    session_factory = get_session_factory()
    with session_factory() as db_session:
        class_args = {}

        if "db_session" in command_class.__annotations__:
            class_args = {"db_session": db_session}

        debug(command_class, class_args)
        command = command_class(**class_args)
        debug(command)
        result = command.call(*args)
        debug(result)
        return result


def setup(ctx: SetupContext):
    ctx.add_route("/rpc", handle_rpc, methods=["POST"])
