# Copyright (c) 2023-2024, Abilian SAS
from collections.abc import Callable
from types import ModuleType

import rpyc
from hop3_server.utils.scanner import scan_packages

PACKAGES = [
    "hop3_server.commands",
]

modules = list(scan_packages(PACKAGES))


class Hop3Service(rpyc.Service):
    modules: list[ModuleType]
    commands: dict[str, Callable]

    def __init__(self):
        self.modules = list(scan_packages(PACKAGES))
        for mod in self.modules:
            assert isinstance(mod, ModuleType)
            for name in dir(mod):
                if name.startswith("cmd_"):
                    cmd = getattr(mod, name)
                    if callable(cmd):
                        self.commands[name[4:]] = cmd

    def on_connect(self, conn):
        pass

    def on_disconnect(self, conn):
        pass

    def exposed_rpc(self, command, *args, **kwargs):
        cmd = self.commands.get(command)
        if cmd is None:
            msg = f"Command {command} not found"
            raise ValueError(msg)
        return cmd(*args, **kwargs)

    def get_module(self, name):
        for mod in self.modules:
            if mod.__name__ == name:
                return mod
