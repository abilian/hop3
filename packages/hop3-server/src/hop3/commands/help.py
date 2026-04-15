# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

from typing import ClassVar

from hop3.lib.registry import lookup, register

from ._base import Command
from ._response import data, error, text


@register
class HelpCmd(Command):
    """Display useful help messages.

    Usage:
        hop help                  Show top-level commands
        hop help <command>        Show detailed help for a command
        hop help <ns> <verb>      Show detailed help for a namespaced command
        hop help --all            Show all commands including subcommands

    Examples:
        hop help auth             Show auth command help and its subcommands
        hop help config set       Show help for 'config set' command
    """

    name: ClassVar[tuple[str, ...]] = ("help",)
    requires_auth: ClassVar[bool] = False  # Public command

    def call(self, *args):
        # Parse --all flag
        arg_list = list(args)
        show_all = "--all" in arg_list
        if show_all:
            arg_list.remove("--all")

        # If a command name is provided, show detailed help for that command.
        # Remaining tokens form the command path tuple (e.g., ("config", "set")).
        if arg_list:
            return self._detailed_help(tuple(arg_list))

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

        # Find top-level (single-token) commands and count subcommands of each namespace
        top_level_cmds: dict[str, type[Command]] = {}
        subcommand_counts: dict[str, int] = {}

        for cmd in commands:
            # Skip hidden commands (internal/technical)
            if getattr(cmd, "hidden", False):
                continue
            name = cmd.name
            if not name:
                continue
            if len(name) == 1:
                # Top-level command or namespace root
                top_level_cmds[name[0]] = cmd
            else:
                # This is a subcommand; count it under its namespace root
                prefix = name[0]
                subcommand_counts[prefix] = subcommand_counts.get(prefix, 0) + 1

        # Build output
        for display in sorted(top_level_cmds.keys()):
            cmd = top_level_cmds[display]
            help_text = self._get_short_help(cmd.__doc__)
            output.append(f"  {display:<16} {help_text}")

        output.append("")
        output.append("Use 'hop help <command>' to see subcommands and detailed help.")

        return [text("\n".join(output))]

    def _show_all_commands(self):
        """Show all commands including subcommands (full listing)."""
        output = [
            "USAGE",
            "  $ hop <command> <args>",
            "  $ hop help <command>    # Show help for a command",
            "  $ hop help --all        # Show all commands including subcommands",
            "",
            "ALL COMMANDS",
        ]

        commands = lookup(Command)
        commands.sort(key=lambda cmd: cmd.name)
        for cmd in commands:
            # Skip hidden commands (internal/technical)
            if getattr(cmd, "hidden", False):
                continue
            display = " ".join(cmd.name)
            help_text = self._get_short_help(cmd.__doc__)
            output.append(f"  {display:<24} {help_text}")

        return [text("\n".join(output))]

    def _detailed_help(self, command_name: tuple[str, ...]):
        """Show detailed help for a specific command.

        If the command has subcommands, they will be listed as well.
        If the tokens don't exactly match a command, we try the longest matching
        prefix (so `help run myapp` still finds `run`, and `help config show foo`
        finds `config show`).

        Args:
            command_name: Tuple of tokens identifying the command (e.g., ("config", "set"))

        Returns:
            Formatted help output for the command
        """
        all_commands = lookup(Command)
        commands = {cmd.name: cmd for cmd in all_commands}

        # Try longest-prefix match so extra positional args don't break help.
        matched: tuple[str, ...] | None = None
        for n in range(len(command_name), 0, -1):
            key = command_name[:n]
            if key in commands:
                matched = key
                break

        display = " ".join(command_name)
        if matched is None:
            return [
                error(f"Unknown command: {display}"),
                text("\nRun 'hop help' to see all available commands."),
            ]
        command_name = matched
        display = " ".join(command_name)

        cmd = commands[command_name]
        docstring = cmd.__doc__ or "No help available for this command."

        output = [
            f"COMMAND: {display}",
            "",
            docstring.strip(),
        ]

        # Find subcommands: commands whose name has this command name as a strict prefix.
        # Exclude hidden subcommands.
        subcommands = [
            c
            for c in all_commands
            if len(c.name) > len(command_name)
            and c.name[: len(command_name)] == command_name
            and not getattr(c, "hidden", False)
        ]

        if subcommands:
            subcommands.sort(key=lambda c: c.name)
            output.append("")
            output.append("SUBCOMMANDS")
            for sub in subcommands:
                sub_display = " ".join(sub.name)
                help_text = self._get_short_help(sub.__doc__)
                output.append(f"  {sub_display:<28} {help_text}")

        return [text("\n".join(output))]

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


@register
class HelpCommandsCmd(Command):
    """Return list of available command names for shell completion.

    Returns a JSON-serializable list of all non-hidden command names.
    Used by the CLI to generate and cache shell completion scripts.

    Usage:
        hop help commands

    Output:
        {"commands": ["addon", "addon attach", "app", "app logs", ...]}
    """

    name: ClassVar[tuple[str, ...]] = ("help", "commands")
    requires_auth: ClassVar[bool] = False  # Public command
    hidden: ClassVar[bool] = True  # RPC endpoint, not user-facing

    def call(self, *args):
        """Return list of command names (as space-joined strings) as structured data."""
        commands = lookup(Command)
        command_names = sorted(
            " ".join(cmd.name)
            for cmd in commands
            if not getattr(cmd, "hidden", False)
        )

        return [data({"commands": command_names})]
