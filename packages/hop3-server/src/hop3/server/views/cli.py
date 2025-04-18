# Copyright (c) 2025, Abilian SAS
"""
Simple endpoint for debugging.

Use with:

```shell
curl -X POST http://localhost:8000/cli -d '--help'
```

"""

from __future__ import annotations

import traceback

from devtools import debug
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from hop3.commands import Command
from hop3.lib.registry import lookup
from hop3.lib.scanner import scan_package
from hop3.orm import get_session_factory
from hop3.server.singletons import router

scan_package("hop3.commands")
commands = {command.name: command for command in lookup(Command)}


@router.post("/cli")
async def cli(request: Request):
    """
    CLI view (for debugging).
    """
    body = await request.body()
    args = body.decode("utf-8").split()
    command = args.pop(0)

    try:
        result = call(command, args)
    except ValueError as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

    return PlainTextResponse(str(result))


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
