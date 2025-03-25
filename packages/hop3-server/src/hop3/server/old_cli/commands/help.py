# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

from hop3.lib.decorators import command
from hop3.server.commands.help import print_help


@command
class HelpCmd:
    """Display help information for the Hop3 CLI."""

    def run(self):
        print_help()
