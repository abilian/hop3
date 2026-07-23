# Copyright (c) 2024-2025, Abilian SAS

"""
Help output rendering (ADR 036 D4, D11, D19).

`hop3 help` (bare) renders top-level commands grouped by task category; the
client then injects local commands (see `hop3_cli/commands/help.py`) and
appends a status-line + feedback-link footer. `hop3 help <cmd ...>` renders
a structured page with USAGE -> EXAMPLES -> POSITIONAL -> OPTIONS -> SEE ALSO
sections. `hop3 help --all` lists every command flat, with `[top]` /
`[namespace]` / `[alias]` markers (aliases point at their canonical name).
"""

from __future__ import annotations

from typing import ClassVar

from hop3.lib.console import get_verbosity
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
        "catalog",
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
    """
    Display useful help messages.

    Usage:
        hop help                  Show top-level commands grouped by category
        hop help <command>        Show detailed help for a command
        hop help <ns> <verb>      Show detailed help for a namespaced command
        hop help --all            Show all commands flat with markers
        hop help --all -v         Show the full help for every command

    Examples:
        hop help auth             Show auth command help and its subcommands
        hop help config set       Show help for 'config set' command
    """

    name: ClassVar[tuple[str, ...]] = ("help",)
    requires_auth: ClassVar[bool] = False  # Public command

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        arg_list = list(args)
        show_all = "--all" in arg_list
        if show_all:
            arg_list.remove("--all")

        # If a command name is provided, show detailed help for that command.
        # Remaining tokens form the command path tuple (e.g., ("config", "set")).
        if arg_list:
            return self._detailed_help(tuple(arg_list))

        if show_all:
            # `--all -v` (verbosity is forwarded from the client and applied as
            # a context; see rpc.call) aggregates the full help for every
            # command. Plain `--all` keeps the terse flat index (ADR 036).
            if get_verbosity() >= 2:
                return self._show_all_commands_verbose()
            return self._show_all_commands()
        return self._show_top_level_commands()

    def _show_top_level_commands(self) -> list[dict]:
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

    def _show_all_commands(self) -> list[dict]:
        """Show all commands flat, alphabetical, with `[top]` / `[ns]` markers."""
        output = [
            "USAGE",
            "  $ hop <command> <args>",
            "  $ hop help <command>    # Show help for a command",
            "  $ hop help --all        # Show all commands flat",
            "",
            "ALL COMMANDS",
        ]

        commands = [cmd for cmd in lookup(Command) if not getattr(cmd, "hidden", False)]
        canonical_names = {cmd.name for cmd in commands}

        # Build the flat index: every canonical command, plus each of its
        # aliases tagged `[alias]` and pointing at the canonical spelling, so
        # aliases (`logs` -> `app logs`, `domains` -> `domain`, `apps` ->
        # `app list`, ...) are discoverable here instead of silently working
        # but never listed. Entries are (name_tuple, marker, help_text).
        entries: list[tuple[tuple[str, ...], str, str]] = []
        for cmd in commands:
            marker = "[top]" if len(cmd.name) == 1 else f"[{cmd.name[0]}]"
            entries.append((cmd.name, marker, self._get_short_help(cmd.__doc__)))
            canonical = " ".join(cmd.name)
            for alias in getattr(cmd, "aliases", []):
                if alias in canonical_names:
                    continue  # a real command owns this name; it wins.
                entries.append((alias, "[alias]", f"→ {canonical}"))

        entries.sort()  # by name tuple (first element); names are unique

        # Width the name column to the longest entry so the marker column lines
        # up even for long names (e.g. "addon postgres credentials"). The client
        # aligns its injected local commands to the same column — it auto-detects
        # this width from the first marker bracket (see hop3_cli.commands.help).
        name_width = max((len(" ".join(name)) for name, _, _ in entries), default=22)
        for name, marker, help_text in entries:
            display = " ".join(name)
            output.append(f"  {display:<{name_width}} {marker:<10} {help_text}")

        output.append("")
        output.append(
            "Use 'hop help --all -v' to print the full help for every command."
        )
        return [text("\n".join(output))]

    def _show_all_commands_verbose(self) -> list[dict]:
        """
        Aggregate the full detailed help for every command, recursively.

        `hop help --all -v` renders, for each non-hidden command (top-level and
        namespaced), the same D11 page produced by `hop help <command>`, joined
        with separators. This is the long "manual" view of the whole CLI.
        """
        all_commands = lookup(Command)
        visible = sorted(
            (cmd for cmd in all_commands if not getattr(cmd, "hidden", False)),
            key=lambda cmd: cmd.name,
        )

        separator = "=" * 72
        output = [
            "ALL COMMANDS — FULL HELP",
            "",
            f"Full help for every command ({len(visible)} total), recursively.",
            "Use 'hop help <command>' to view a single entry.",
            "",
        ]
        for cmd in visible:
            output.append(separator)
            output.append("")
            output.extend(self._render_command_block(all_commands, cmd, cmd.name))
            output.append("")

        return [text("\n".join(output).rstrip() + "\n")]

    def _detailed_help(self, command_name: tuple[str, ...]) -> list[dict]:
        """
        Show detailed help for a specific command, in D11 section order.

        Format: USAGE -> EXAMPLES -> (DESCRIPTION) -> SUBCOMMANDS -> Part of.
        Sections are parsed from the command's docstring; the first non-empty
        line is the one-liner summary shown at the top.
        """
        all_commands = lookup(Command)
        commands = {cmd.name: cmd for cmd in all_commands}
        # Also resolve server-side aliases (e.g. `run` -> `app run`,
        # `destroy` -> `app destroy`) so `hop3 <alias> --help` works instead
        # of reporting "Unknown command". Canonical names take precedence.
        for cmd in all_commands:
            for alias in getattr(cmd, "aliases", []):
                commands.setdefault(alias, cmd)

        matched = _longest_prefix_match(command_name, commands)
        if matched is None:
            return [
                error(f"Unknown command: {' '.join(command_name)}"),
                text("\nRun 'hop help' to see all available commands."),
            ]

        cmd = commands[matched]
        output = self._render_command_block(all_commands, cmd, matched)
        # If reached via an alias (matched tuple differs from the canonical
        # name), say so up front so the user isn't surprised the help page is
        # titled differently from what they typed.
        if matched != cmd.name:
            typed = " ".join(matched)
            canonical = " ".join(cmd.name)
            output = [f"`{typed}` is an alias for `{canonical}`.", "", *output]
        return [text("\n".join(output))]

    def _render_command_block(
        self,
        all_commands: list[type[Command]],
        cmd: type[Command],
        display_name: tuple[str, ...],
    ) -> list[str]:
        """
        Render one command's D11 help page as a list of lines.

        Shared by `_detailed_help` (single command) and
        `_show_all_commands_verbose` (every command) so the two stay in sync.
        """
        display = " ".join(display_name)
        sections = _parse_docstring_sections(cmd.__doc__)
        output = _render_detailed_help(display, sections)
        output.extend(
            _render_subcommands(all_commands, display_name, self._get_short_help)
        )

        # "Part of:" line for namespaced commands.
        if len(display_name) > 1:
            output.append(f"Part of: hop {display_name[0]} namespace.")

        return output

    # Kept as a static method so tests using HelpCmd._get_short_help(...) still work.
    _get_short_help = staticmethod(_short_help)


@register
class HelpCommandsCmd(Command):
    """
    Return list of available command names for shell completion.

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

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        """Return list of command names (as space-joined strings) as structured data."""
        commands = lookup(Command)
        command_names = sorted(
            " ".join(cmd.name) for cmd in commands if not getattr(cmd, "hidden", False)
        )

        return [data({"commands": command_names})]


# Helpers are in `_help_render.py` (shared with `_base.Command.get_help`).
