# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

from typing import ClassVar

from hop3.lib.console import bold
from hop3.lib.registry import lookup, register

from ._base import Command

HELP_XXX = """
COMMANDS
  apps            List apps (running or stopped).
  backup          Run a backup for an app.
  config          Manage app config. Type 'hop config' for help.
  deploy          Deploy app.
  destroy         Destroy app, remove all files.
  help            Display help information for the Hop3 CLI.
  logs            Tail running logs, e.g: hop-agent logs <app> [<process>].
  pg              Manage a PostgreSQL database.
  plugins         List installed plugins.
  ps              Show process count for app.
  redis           Manage Redis commands.
  restart         Restart an app.
  run             Run command in the context of app, e.g.: hop run ls -- -al.
  sbom            Generate a SBOM for an app.
  setup           Initialize environment.
  start           Stop an app.
  stop            Stop an app.
"""


@register
class HelpCmd(Command):
    """Display useful help messages."""

    name: ClassVar[str] = "help"
    requires_auth: ClassVar[bool] = False  # Public command

    def call(self, *args):
        # If a command name is provided, show detailed help for that command
        if args:
            command_name = args[0]
            return self._detailed_help(command_name)

        # Otherwise, show overview of all commands
        output = [
            bold("USAGE"),
            "  $ hop <command> <args>",
            "  $ hop help <command>  # Show detailed help for a command",
            "",
            bold("COMMANDS"),
        ]

        commands = lookup(Command)
        commands.sort(key=lambda cmd: cmd.name)
        for cmd in commands:
            cmd_name = cmd.name
            # Extract only the first line of the docstring for the overview
            # Full docstring is available when asking for help on a specific command
            help_text = self._get_short_help(cmd.__doc__)
            output.append(f"  {cmd_name:<20} {help_text}")

        return [
            {"t": "text", "text": "\n".join(output)},
        ]

    def _detailed_help(self, command_name: str):
        """Show detailed help for a specific command.

        Args:
            command_name: The name of the command to show help for

        Returns:
            Formatted help output for the command
        """
        commands = {cmd.name: cmd for cmd in lookup(Command)}

        if command_name not in commands:
            return [
                {"t": "error", "text": f"Unknown command: {command_name}"},
                {
                    "t": "text",
                    "text": "\nRun 'hop help' to see all available commands.",
                },
            ]

        cmd = commands[command_name]
        docstring = cmd.__doc__ or "No help available for this command."

        output = [
            bold(f"COMMAND: {command_name}"),
            "",
            docstring.strip(),
        ]

        return [
            {"t": "text", "text": "\n".join(output)},
        ]

    @staticmethod
    def _get_short_help(docstring: str | None) -> str:
        """Extract the first line (short summary) from a docstring.

        Convention: The first line of a command's docstring should be a brief
        one-line summary. This is shown in the command overview. The rest of
        the docstring provides detailed help shown when asking for specific
        command help.

        Args:
            docstring: The command's docstring

        Returns:
            The first line of the docstring, stripped of whitespace
        """
        if not docstring:
            return ""

        # Split by newlines and get the first non-empty line
        lines = docstring.strip().split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped:
                return stripped

        return ""
