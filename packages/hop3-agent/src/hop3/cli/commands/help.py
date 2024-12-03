# Copyright (c) 2024, Abilian SAS

from __future__ import annotations

from hop3.cli.help import print_help
from hop3.cli.registry import command


@command
class HelpCmd:
    """Display help information for the Hop3 CLI."""

    def run(self):
        print_help()
