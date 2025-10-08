# Copyright (c) 2023-2025, Abilian SAS

"""
Command Docstring Convention
============================

When writing CLI commands, follow this docstring convention:

- **First Line**: A brief one-line summary (shown in ``hop --help`` overview)
- **Blank Line**: Separate the summary from detailed help
- **Detailed Help**: Usage instructions, examples, and detailed description (shown when asking for specific command help)

Example:

.. code-block:: python

    class MyCmd(Command):
        '''Brief one-line summary of what this command does.

        This is the detailed help that includes usage instructions,
        examples, and more detailed explanations.

        Usage: hop mycommand <arg1> <arg2>

        Examples:
            hop mycommand foo bar
            hop mycommand --option value
        '''
"""

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
