# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

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

    name = "help"

    def call(self, *args):
        output = [
            bold("USAGE"),
            "  $ hop <command> <args>",
            "",
            bold("COMMANDS"),
        ]

        commands = lookup(Command)
        commands.sort(key=lambda cmd: cmd.name)
        for cmd in commands:
            cmd_name = cmd.name
            help_text = cmd.__doc__ or ""
            output.append(f"  {cmd_name:<20} {help_text}")

        return [
            {"t": "text", "text": "\n".join(output)},
        ]
