# Copyright (c) 2025, Abilian SAS
from __future__ import annotations


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
                return subcommand.call(*args[1:])

        return self.get_help()

    def get_help(self):
        subcommands = self.subcommands()
        subcommand_names = sorted(subcommand.name for subcommand in subcommands)
        return [
            {"t": "text", "text": "Unknown subcommand"},
            {
                "t": "text",
                "text": "Available subcommands: " + ", ".join(subcommand_names),
            },
        ]
