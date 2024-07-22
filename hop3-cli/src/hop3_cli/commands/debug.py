from __future__ import annotations

from pprint import pprint

from . import Command
from ..config import get_config


class DebugCommand(Command):
    """Show debug information (for developers)."""

    name = "debug"

    def handle(self, args):
        config = get_config(args.config_file)
        print("Config:")
        pprint(config.data)
