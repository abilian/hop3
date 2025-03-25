# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

from importlib.metadata import version

from attrs import frozen

from hop3.lib.console import bold
from hop3.server.commands.registry import COMMAND_REGISTRY


def print_help():
    """Display the help information for the Hop3 command-line interface (CLI).

    This gathers and prints the version, usage instructions, and
    available commands.
    """
    package_version = version("hop3-server")

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
        name = get_command_name(cmd)

        if ":" in name:
            continue

        help_text = cmd.__doc__ or ""
        if "INTERNAL" in help_text:
            # Skip internal commands
            continue

        output.append(f"  {name:<15} {help_text}")

    print("\n".join(output))


@frozen
class Help:
    command_name: str

    def __call__(self):
        output = [
            bold("USAGE"),
            f"  $ hop {self.command_name} ...",
            "",
            bold("COMMANDS"),
        ]

        # Iterate over the commands in the COMMAND_REGISTRY, sorted by the command's name
        for cmd in sorted(COMMAND_REGISTRY.values(), key=lambda cmd: cmd.__name__):
            name = get_command_name(cmd)

            if ":" not in name:
                continue

            primary_name = name.split(":")[0]
            if primary_name != self.command_name:
                continue

            help_text = cmd.__doc__ or ""
            if "INTERNAL" in help_text:
                # Skip internal commands
                continue

            output.append(f"  {name:<20} {help_text}")

        print("\n".join(output))


def get_command_name(cmd):
    name = getattr(cmd, "name", None)
    if not name:
        # If no name attribute, use the command's class name without 'Cmd' and in lowercase
        name = cmd.__name__.replace("Cmd", "").lower()
    return name
