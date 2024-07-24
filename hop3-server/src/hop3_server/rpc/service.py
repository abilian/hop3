# Copyright (c) 2023-2024, Abilian SAS

from pprint import pprint
from types import ModuleType

import rpyc
from hop3_server.utils.scanner import scan_packages

PACKAGES = [
    "hop3_server.commands",
]

modules = list(scan_packages(PACKAGES))
pprint(modules)


class Hop3Service(rpyc.Service):
    modules: list[ModuleType]

    def __init__(self):
        self.modules = list(scan_packages(PACKAGES))
        for mod in self.modules:
            assert isinstance(mod, ModuleType)
        # super().__init__()

    def on_connect(self, conn):
        pass

    def on_disconnect(self, conn):
        pass

    def exposed_rpc(self, module_name, command, *args, **kwargs):
        module = self.get_module(module_name)
        cmd = getattr(module, f"cmd_command", None)
        if cmd is None:
            msg = f"Command {command} not found in module {module_name}"
            raise ValueError(msg)
        if not callable(cmd):
            msg = f"Command {command} in module {module_name} is not callable"
            raise ValueError(msg)

        return cmd(*args, **kwargs)

    def get_module(self, name):
        for mod in self.modules:
            if mod.__name__ == name:
                return mod
