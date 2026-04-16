# Copyright (c) 2024-2025, Abilian SAS

"""Help output rendering (ADR 036 D4, D11, D19).

`hop3 help` (bare) renders top-level commands grouped by task category; the
client then injects local commands (see `hop3_cli/commands/help.py`) and
appends a status-line + feedback-link footer. `hop3 help <cmd ...>` renders
a structured page with USAGE -> EXAMPLES -> POSITIONAL -> OPTIONS -> SEE ALSO
sections. `hop3 help --all` lists every command flat, with `[top]` /
`[namespace]` markers.
"""

from __future__ import annotations

from typing import ClassVar

from hop3.lib.registry import lookup, register

from ._base import Command
from ._help_render import (
    longest_prefix_match as _longest_prefix_match,
    parse_docstring_sections as _parse_docstring_sections,
    render_detailed_help as _render_detailed_help,
    render_subcommands as _render_subcommands,
    short_help as _short_help,
)
from ._response import data, error, text

# ADR 036 D4 / D11: task-oriented categorization of the top-level surface.
# Keys are displayed in the order below. Every top-level command should
# appear in exactly one category; anything unmatched falls through to OTHER.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "DAILY OPERATIONS": (
        "deploy",
        "logs",
        "run",
        "restart",
        "status",
        "ps",
        "scale",
        "ssh",
        "open",
    ),
    "MANAGEMENT": (
        "app",
        "addon",
        "backup",
        "config",
        "context",
        "user",
    ),
    "ADMINISTRATION": (
        "system",
        "auth",
        "plugin",
    ),
    "UTILITIES": (
        "help",
        "version",
    ),
}

# Reverse lookup: command name -> category. Built lazily.
_NAME_TO_CATEGORY: dict[str, str] = {
    name: cat for cat, names in CATEGORIES.items() for name in names
}


def _category_for(name: str) -> str:
    """Return the category for a top-level command name, or 'OTHER' if unmatched."""
    return _NAME_TO_CATEGORY.get(name, "OTHER")


@register
class HelpCmd(Command):
    """Display useful help messages.

    Usage:
        hop help                  Show top-level commands grouped by category
        hop help <command>        Show detailed help for a command
        hop help <ns> <verb>      Show detailed help for a namespaced command
        hop help --all            Show all commands flat with markers

    Examples:
        hop help auth             Show auth command help and its subcommands
        hop help config set       Show help for 'config set' command
    """

    name: ClassVar[tuple[str, ...]] = ("help",)
    requires_auth: ClassVar[bool] = False  # Public command

    def call(self, *args):
        arg_list = list(args)
        show_all = "--all" in arg_list
        if show_all:
            arg_list.remove("--all")

        # If a command name is provided, show detailed help for that command.
        # Remaining tokens form the command path tuple (e.g., ("config", "set")).
        if arg_list:
            return self._detailed_help(tuple(arg_list))

        if show_all:
            return self._show_all_commands()
        return self._show_top_level_commands()

    def _show_top_level_commands(self):
        """Show top-level commands grouped by category (ADR 036 D11)."""
        output = [
            "USAGE",
            "  $ hop <command> <args>",
            "  $ hop help <command>    # Show help for a command",
            "  $ hop help --all        # Show all commands flat",
            "",
        ]

        commands = lookup(Command)

        # Collect top-level (single-token) non-hidden commands.
        top_level: dict[str, type[Command]] = {}
        for cmd in commands:
            if getattr(cmd, "hidden", False):
                continue
            if cmd.name and len(cmd.name) == 1:
                top_level[cmd.name[0]] = cmd

        # Bucket by category, preserving the CATEGORIES order.
        buckets: dict[str, list[tuple[str, type[Command]]]] = {}
        for name in sorted(top_level):
            cat = _category_for(name)
            buckets.setdefault(cat, []).append((name, top_level[name]))

        category_order = [*CATEGORIES.keys(), "OTHER"]
        for category in category_order:
            if category not in buckets:
                continue
            output.append(category)
            for display, cmd in buckets[category]:
                help_text = self._get_short_help(cmd.__doc__)
                output.append(f"  {display:<16} {help_text}")
            output.append("")

        output.append("Use 'hop help <command>' to see subcommands and detailed help.")
        return [text("\n".join(output))]

    def _show_all_commands(self):
        """Show all commands flat, alphabetical, with `[top]` / `[ns]` markers."""
        output = [
            "USAGE",
            "  $ hop <command> <args>",
            "  $ hop help <command>    # Show help for a command",
            "  $ hop help --all        # Show all commands flat",
            "",
            "ALL COMMANDS",
        ]

        commands = lookup(Command)
        commands.sort(key=lambda cmd: cmd.name)
        for cmd in commands:
            if getattr(cmd, "hidden", False):
                continue
            display = " ".join(cmd.name)
            help_text = self._get_short_help(cmd.__doc__)
            marker = "[top]" if len(cmd.name) == 1 else f"[{cmd.name[0]}]"
            # 24-char name column, 8-char marker column.
            output.append(f"  {display:<24} {marker:<10} {help_text}")

        return [text("\n".join(output))]

    def _detailed_help(self, command_name: tuple[str, ...]):
        """Show detailed help for a specific command, in D11 section order.

        Format: USAGE -> EXAMPLES -> (DESCRIPTION) -> SUBCOMMANDS -> Part of.
        Sections are parsed from the command's docstring; the first non-empty
        line is the one-liner summary shown at the top.
        """
        all_commands = lookup(Command)
        commands = {cmd.name: cmd for cmd in all_commands}

        matched = _longest_prefix_match(command_name, commands)
        if matched is None:
            return [
                error(f"Unknown command: {' '.join(command_name)}"),
                text("\nRun 'hop help' to see all available commands."),
            ]

        cmd = commands[matched]
        display = " ".join(matched)
        sections = _parse_docstring_sections(cmd.__doc__)
        output = _render_detailed_help(display, sections)
        output.extend(_render_subcommands(all_commands, matched, self._get_short_help))

        # "Part of:" line for namespaced commands.
        if len(matched) > 1:
            output.append(f"Part of: hop {matched[0]} namespace.")

        return [text("\n".join(output))]

    # Kept as a static method so tests using HelpCmd._get_short_help(...) still work.
    _get_short_help = staticmethod(_short_help)


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
            " ".join(cmd.name) for cmd in commands if not getattr(cmd, "hidden", False)
        )

        return [data({"commands": command_names})]


# Helpers are in `_help_render.py` (shared with `_base.Command.get_help`).
