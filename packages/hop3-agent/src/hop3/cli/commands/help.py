# Copyright (c) 2024, Abilian SAS

from __future__ import annotations

from importlib.metadata import version

from hop3.cli.registry import COMMAND_REGISTRY, command
from hop3.util.console import bold


@command
class HelpCmd:
    """Display help information for the Hop3 CLI."""

    def run(self):
        print_help()


def print_help():
    """Display the help information for the Hop3 command-line interface (CLI).

    This gathers and prints the version, usage instructions, and
    available commands for the Hop3 CLI.
    """
    package_version = version("hop3-agent")

    output = [
        "CLI to interact with Hop3",
        "",
        bold("VERSION"),
        f"  {package_version}",
        "",
        bold("USAGE"),
        "  $ hop [COMMAND]",
        "",
        bold("COMMANDS"),
    ]

    # Iterate over the commands in the COMMAND_REGISTRY, sorted by the command's name
    for cmd in sorted(COMMAND_REGISTRY.values(), key=lambda cmd: cmd.__name__):
        name = getattr(cmd, "name", None)
        if not name:
            # If no name attribute, use the command's class name without 'Cmd' and in lowercase
            name = cmd.__name__.replace("Cmd", "").lower()
        help_text = cmd.__doc__ or ""
        if "INTERNAL" in help_text:
            # Skip commands marked as internal
            continue
        output.append(f"  {name:<15} {help_text}")

    print("\n".join(output))
