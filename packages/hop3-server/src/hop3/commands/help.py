# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

from devtools import debug

from hop3.lib.console import bold
from hop3.lib.registry import lookup, register

from ._base import Command


@register
class HelpCommand(Command):
    """Display useful help messages."""

    name = "help"

    def call(self, *args):
        output = [
            bold("USAGE"),
            f"  $ hop {self.name} ...",
            "",
            bold("COMMANDS"),
        ]

        commands = lookup(Command)
        debug(commands)
        commands.sort(key=lambda cmd: cmd.name)
        for cmd in commands:
            name = cmd.name

            if ":" not in name:
                continue

            primary_name = name.split(":")[0]
            if primary_name != self.name:
                continue

            help_text = cmd.__doc__ or ""
            output.append(f"  {name:<20} {help_text}")

        return [
            {"t": "text", "text": "\n".join(output)},
        ]
