# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from collections.abc import Callable

from devtools import debug
from hop3_server.commands.base import scan_commands


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
