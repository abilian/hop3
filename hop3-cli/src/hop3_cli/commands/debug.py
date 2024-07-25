# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pprint import pprint

from . import Command


class DebugCommand(Command):
    """Show debug information (for developers)."""

    name = "debug"

    def handle(self, args, context):
        config = context.config
        print("Config:")
        pprint(config.data)
