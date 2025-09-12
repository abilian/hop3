# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from typing import ClassVar

from hop3.lib.console import bold
from hop3.lib.registry import lookup


class Command:
    name: ClassVar[str] = ""

    def call(self, *args):
        return self.get_help()

    def get_help(self):
        output = [
            bold("USAGE"),
            f"  $ hop {self.name} <args>",
            "",
            bold("COMMANDS"),
        ]
        commands = lookup(Command)
        commands.sort(key=lambda cmd: cmd.name)
        for cmd in commands:
            cmd_name = cmd.name

            if ":" not in cmd_name:
                # Skip commands that are not subcommands
                continue
            primary_name = cmd_name.split(":")[0]
            if primary_name != self.name:
                continue

            help_text = cmd.__doc__ or ""
            output.append(f"  {cmd_name:<20} {help_text}")

        return [
            {"t": "text", "text": "\n".join(output)},
        ]

    def subcommands(self):
        return []

    # def get_help(self):
    #     subcommands = self.subcommands()
    #     subcommand_names = sorted(subcommand.name for subcommand in subcommands)
    #     return [
    #         {"t": "text", "text": "Unknown subcommand"},
    #         {
    #             "t": "text",
    #             "text": "Available subcommands: " + ", ".join(subcommand_names),
    #         },
    #     ]
