# Copyright (c) 2023-2024, Abilian SAS

from types import ModuleType
from typing import cast

from hop3_server.utils.scanner import scan_packages

PACKAGES = [
    "hop3_server.commands",
]


class Command:
    name: str = ""

    def subcommands(self):
        return []

    def call(self, *args):
        if not args:
            return self.get_help()

        subcommands = self.subcommands()
        for subcommand in subcommands:
            if subcommand.name == args[0]:
                return subcommand.call(args[1:])

        return self.get_help()

    def get_help(self):
        subcommands = self.subcommands()
        subcommand_names = sorted(subcommand.name for subcommand in subcommands)
        return [
            {"t": "text", "text": "Unknown subcommand"},
            {"t": "text", "text": "Available subcommands: " + ", ".join(subcommand_names)},
        ]


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
            command = cast(type[Command], obj)
            if command.name:
                name = command.name
            else:
                name = command.__name__.lower()
            commands[name] = command
    return commands
