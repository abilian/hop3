# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import traceback
from collections.abc import Callable

from devtools import debug
from hop3_server.commands.base import scan_commands
from jsonrpcserver import Error, Success, method


class Hop3Service:
    commands: dict[str, Callable]

    def __init__(self):
        self.commands = scan_commands()

    def call(self, command, args):
        cmd = self.commands.get(command)
        if cmd is None:
            msg = f"Command {command} not found"
            raise ValueError(msg)

        cmd_obj = cmd()
        debug(cmd_obj)
        result = cmd_obj.call(*args)
        debug(result)
        return result


@method
def cli(args):
    debug(args)
    command = args[0]
    extra_args = args[1:]

    service = Hop3Service()
    try:
        result = service.call(command, extra_args)
        return Success(result)
    except Exception as e:
        traceback.print_exc()
        return Error(message=str(e))
