from __future__ import annotations

from importlib.metadata import version as importlib_version

from . import Command


class HelpCommand(Command):
    """Show help."""

    name = "help"

    def handle(self, args, context):
        pass


class VersionCommand(Command):
    """Show the currently installed Hop3 version."""

    name = "version"

    def handle(self, args, context):
        print("CLI version:", importlib_version("hop3-cli"))
