# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import json
import traceback
from typing import TYPE_CHECKING

from devtools import debug
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from hop3_server.commands.base import scan_commands

if TYPE_CHECKING:
    from starlette.requests import Request

COMMANDS = scan_commands()


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


def call(command, args):
    debug(command, args)
    cmd = COMMANDS.get(command)
    if cmd is None:
        msg = f"Command {command} not found"
        raise ValueError(msg)

    cmd_obj = cmd()
    debug(cmd_obj)
    result = cmd_obj.call(*args)
    debug(result)
    return result


async def handle_home(request: Request):  # noqa: RUF029
    return JSONResponse({"message": "Hello, world!"})


routes = [
    Route("/", handle_home),
    Route("/rpc", handle_rpc, methods=["POST"]),
]
