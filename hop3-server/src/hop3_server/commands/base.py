# Copyright (c) 2023-2024, Abilian SAS

from abc import ABC, abstractmethod
from types import ModuleType

from hop3_server.utils.scanner import scan_packages

PACKAGES = [
    "hop3_server.commands",
]


class Command(ABC):
    @abstractmethod
    def call(self, *args):
        raise NotImplementedError


def scan_commands():
    commands = {}
    modules = list(scan_packages(PACKAGES))
    for mod in modules:
        assert isinstance(mod, ModuleType)
        for obj in vars(mod).values():
            if not isinstance(obj, type):
                continue
            if not issubclass(obj, Command):
                continue
            if obj == Command:
                continue
            name = obj.__name__.lower()
            commands[name] = obj
    return commands
