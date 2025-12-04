# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

from typing import ClassVar

from hop3.lib.registry import lookup, register

from ._base import Command


@register
class HelpCmd(Command):
    """Display useful help messages.

    Usage:
        hop help              Show top-level commands
        hop help <command>    Show detailed help for a command
        hop help --all        Show all commands including subcommands

    Examples:
        hop help auth         Show auth command help and its subcommands
        hop help config:set   Show help for config:set command
    """

    name: ClassVar[str] = "help"
    requires_auth: ClassVar[bool] = False  # Public command

    def call(self, *args):
        # Parse --all flag
        arg_list = list(args)
        show_all = "--all" in arg_list
        if show_all:
            arg_list.remove("--all")

        # If a command name is provided, show detailed help for that command
        if arg_list:
            command_name = arg_list[0]
            return self._detailed_help(command_name)

        # Show commands overview
        if show_all:
            return self._show_all_commands()
        return self._show_top_level_commands()

    def _show_top_level_commands(self):
        """Show only top-level commands (simplified overview)."""
        output = [
            "USAGE",
            "  $ hop <command> <args>",
            "  $ hop help <command>    # Show help for a command",
            "  $ hop help --all        # Show all commands including subcommands",
            "",
            "COMMANDS",
        ]

        commands = lookup(Command)

        # Find top-level commands and count subcommands
        top_level_cmds: dict[str, type[Command]] = {}
        subcommand_counts: dict[str, int] = {}

        for cmd in commands:
            name = cmd.name
            if ":" in name:
                # This is a subcommand - count it under its prefix
                prefix = name.split(":")[0]
                subcommand_counts[prefix] = subcommand_counts.get(prefix, 0) + 1
            else:
                # This is a top-level command
                top_level_cmds[name] = cmd

        # Build output
        for name in sorted(top_level_cmds.keys()):
            cmd = top_level_cmds[name]
            help_text = self._get_short_help(cmd.__doc__)
            sub_count = subcommand_counts.get(name, 0)

            if sub_count > 0:
                # Add indicator for commands with subcommands
                output.append(f"  {name:<16} {help_text}")
            else:
                output.append(f"  {name:<16} {help_text}")

        output.append("")
        output.append("Use 'hop help <command>' to see subcommands and detailed help.")

        return [
            {"t": "text", "text": "\n".join(output)},
        ]

    def _show_all_commands(self):
        """Show all commands including subcommands (full listing)."""
        output = [
            "USAGE",
            "  $ hop <command> <args>",
            "  $ hop help <command>    # Show help for a command",
            "",
            "ALL COMMANDS",
        ]

        commands = lookup(Command)
        commands.sort(key=lambda cmd: cmd.name)
        for cmd in commands:
            cmd_name = cmd.name
            help_text = self._get_short_help(cmd.__doc__)
            output.append(f"  {cmd_name:<24} {help_text}")

        return [
            {"t": "text", "text": "\n".join(output)},
        ]

    def _detailed_help(self, command_name: str):
        """Show detailed help for a specific command.

        If the command has subcommands, they will be listed as well.

        Args:
            command_name: The name of the command to show help for

        Returns:
            Formatted help output for the command
        """
        all_commands = lookup(Command)
        commands = {cmd.name: cmd for cmd in all_commands}

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
            f"COMMAND: {command_name}",
            "",
            docstring.strip(),
        ]

        # Find subcommands (commands that start with this command name followed by :)
        prefix = command_name + ":"
        subcommands = [c for c in all_commands if c.name.startswith(prefix)]

        if subcommands:
            subcommands.sort(key=lambda c: c.name)
            output.append("")
            output.append("SUBCOMMANDS")
            for sub in subcommands:
                help_text = self._get_short_help(sub.__doc__)
                output.append(f"  {sub.name:<28} {help_text}")

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
