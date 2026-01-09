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

from hop3.lib.registry import lookup


class Command:
    name: ClassVar[str] = ""
    # Authentication metadata (default: requires auth, doesn't need username)
    requires_auth: ClassVar[bool] = True
    pass_username: ClassVar[bool] = False
    # Destructive action metadata (default: not destructive)
    # Set to True for commands that delete/destroy data (requires confirmation)
    destructive: ClassVar[bool] = False

    def call(self, *args, **kwargs):
        return self.get_help()

    def get_help(self):
        output = [
            "USAGE",
            f"  $ hop {self.name} <subcommand>",
            "",
            "SUBCOMMANDS",
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

            help_text = _get_first_line(cmd.__doc__)
            output.append(f"  {cmd_name:<28} {help_text}")

        output.append("")
        output.append(f"Use 'hop {self.name}:<subcommand> --help' for details.")

        return [
            {"t": "text", "text": "\n".join(output)},
        ]

    def subcommands(self):
        return []


def _get_first_line(docstring: str | None) -> str:
    """Extract the first non-empty line from a docstring."""
    if not docstring:
        return ""
    for line in docstring.strip().split("\n"):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""
