# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import rpyc
from cattrs import unstructure
from devtools import debug
from hop3_server.utils.scanner import scan_packages

PACKAGES = [
    "hop3_server.commands",
]

COMMANDS = {}


def scan_commands():
    modules = list(scan_packages(PACKAGES))
    for mod in modules:
        assert isinstance(mod, ModuleType)
        for name in dir(mod):
            if name.startswith("cmd_"):
                cmd = getattr(mod, name)
                if callable(cmd):
                    COMMANDS[name[4:]] = cmd


scan_commands()


class Hop3Service(rpyc.Service):
    modules: list[ModuleType]
    commands: dict[str, Callable]

    def __init__(self):
        self.commands = COMMANDS

    def on_connect(self, conn):
        pass

    def on_disconnect(self, conn):
        pass

    def exposed_rpc(self, command, *args, **kwargs):
        cmd = self.commands.get(command)
        if cmd is None:
            msg = f"Command {command} not found"
            raise ValueError(msg)
        result = cmd(*args, **kwargs)
        dto = unstructure(result)
        debug(dto)
        return dto
