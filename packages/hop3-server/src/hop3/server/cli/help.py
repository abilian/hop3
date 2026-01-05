# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

from argparse import ArgumentParser
from importlib.metadata import version

from attrs import frozen

from hop3.lib.console import bold
from hop3.lib.registry import lookup, register

from ._base import Command


def print_help():
    """Display the help information for the Hop3 command-line interface (CLI).

    This gathers and prints the version, usage instructions, and
    available commands.
    """
    package_version = version("hop3-server")

    output = [
        "CLI to interact with the Hop3 server",
        "",
        bold("VERSION"),
        f"  {package_version}",
        "",
        bold("USAGE"),
        "  $ hop [COMMAND]",
        "",
        bold("COMMANDS"),
    ]

    commands = lookup(Command)
    commands.sort(key=lambda cmd: cmd.__name__)
    for cmd in commands:
        name = get_command_name(cmd)

        if ":" in name:
            continue

        doc = cmd.__doc__ or ""
        if "INTERNAL" in doc:
            # Skip internal commands
            continue

        # Get only first line of docstring
        help_text = doc.strip().split("\n\n")[0].split("\n")[0] if doc else ""

        output.append(f"  {name:<15} {help_text}")

    print("\n".join(output))


@frozen
class Help:
    command_name: str

    def __call__(self):
        output = [
            bold("USAGE"),
            f"  $ hop3-server {self.command_name}:<subcommand> [options]",
            "",
            bold("SUBCOMMANDS"),
        ]

        commands = lookup(Command)
        commands.sort(key=lambda cmd: cmd.__name__)
        for cmd in commands:
            name = get_command_name(cmd)

            if ":" not in name:
                continue

            primary_name = name.split(":")[0]
            if primary_name != self.command_name:
                continue

            doc = cmd.__doc__ or ""
            if "INTERNAL" in doc:
                # Skip internal commands
                continue

            # Get only the first line of docstring
            help_text = doc.strip().split("\n")[0] if doc else ""

            output.append(f"  {name:<24} {help_text}")

        output.append("")
        output.append(
            f"Use 'hop3-server {self.command_name}:<subcommand> --help' for details."
        )

        print("\n".join(output))


def get_command_name(cmd):
    name = getattr(cmd, "name", None)
    if not name:
        # If no name attribute, use the command's class name without 'Cmd' and in lowercase
        name = cmd.__name__.replace("Cmd", "").lower()
    return name


@register
class HelpCommand(Command):
    """Show help information for hop3-server commands."""

    name = "help"

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add command-specific arguments."""
        parser.add_argument(
            "command",
            nargs="?",
            help="Command to show help for (optional)",
        )

    def run(self, command: str | None = None):
        """Show help information.

        Args:
            command: Optional command name to show detailed help for
        """
        if command:
            # Show help for specific command
            self._show_command_help(command)
        else:
            # Show general help
            print_help()

    def _show_command_help(self, command_name: str):
        """Show detailed help for a specific command.

        Args:
            command_name: Name of the command to show help for
        """
        commands = lookup(Command)
        for cmd_class in commands:
            name = get_command_name(cmd_class)
            if name == command_name:
                doc = cmd_class.__doc__ or "No help available."
                print(f"Command: {name}")
                print()
                print(doc.strip())
                return

        # Command not found
        print(f"Error: Command '{command_name}' not found")
        print()
        print("Available commands:")
        for cmd_class in sorted(commands, key=get_command_name):
            name = get_command_name(cmd_class)
            doc = cmd_class.__doc__ or ""
            help_text = doc.strip().split("\n")[0] if doc else ""
            print(f"  {name:<20} {help_text}")
