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

from ._response import text


class Command:
    # Command name as a tuple of tokens (ADR 036 D1/D18). For example:
    #   `hop3 config set` has name = ("config", "set")
    #   `hop3 addon postgres diagnose` has name = ("addon", "postgres", "diagnose")
    # A one-token name (e.g., ("deploy",)) is a top-level command.
    # An empty tuple is the default for the base class only.
    name: ClassVar[tuple[str, ...]] = ()

    # Command aliases: alternative names (also as tuples). Server-side aliases are
    # a legacy mechanism; per ADR 036 D9 the canonical alias table is client-side.
    # Kept here for backward compatibility with a small number of server-registered
    # aliases.
    aliases: ClassVar[list[tuple[str, ...]]] = []

    # Authentication metadata (default: requires auth, doesn't need username)
    requires_auth: ClassVar[bool] = True
    pass_username: ClassVar[bool] = False
    # Destructive action metadata (default: not destructive)
    # Set to True for commands that delete/destroy data (requires confirmation)
    destructive: ClassVar[bool] = False
    # Hidden commands are not shown in help output (for internal/technical commands)
    hidden: ClassVar[bool] = False

    def call(self, *args, **kwargs):
        return self.get_help()

    def get_help(self):
        """Default help output: list subcommands of this namespace."""
        namespace = self.name
        display_name = " ".join(namespace) if namespace else ""
        output = [
            "USAGE",
            f"  $ hop {display_name} <subcommand>",
            "",
            "SUBCOMMANDS",
        ]
        commands = lookup(Command)
        commands.sort(key=lambda cmd: cmd.name)
        for cmd in commands:
            cmd_name = cmd.name

            # Skip commands that are not subcommands of this namespace
            if len(cmd_name) <= len(namespace):
                continue
            if cmd_name[: len(namespace)] != namespace:
                continue

            help_text = _get_first_line(cmd.__doc__)
            sub_display = " ".join(cmd_name)
            output.append(f"  {sub_display:<28} {help_text}")

        output.append("")
        output.append(f"Use 'hop {display_name} <subcommand> --help' for details.")

        return [text("\n".join(output))]

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
