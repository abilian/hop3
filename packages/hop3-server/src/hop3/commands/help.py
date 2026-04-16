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

    @staticmethod
    def _get_short_help(docstring: str | None) -> str:
        """Extract the first non-empty line from a docstring."""
        if not docstring:
            return ""
        for line in docstring.strip().split("\n"):
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
            " ".join(cmd.name) for cmd in commands if not getattr(cmd, "hidden", False)
        )

        return [data({"commands": command_names})]


# ---- Detailed-help rendering helpers ----


def _longest_prefix_match(
    command_name: tuple[str, ...],
    commands: dict,
) -> tuple[str, ...] | None:
    """Find the longest prefix of `command_name` present in `commands`."""
    for n in range(len(command_name), 0, -1):
        key = command_name[:n]
        if key in commands:
            return key
    return None


def _render_detailed_help(display: str, sections: dict) -> list[str]:
    """Render the header + USAGE + EXAMPLES + DESCRIPTION blocks."""
    output: list[str] = []
    header = (
        f"hop {display} — {sections['summary']}" if sections["summary"]
        else f"hop {display}"
    )
    output.append(header)
    output.append("")

    for section_name, lines in (
        ("USAGE", sections["usage"]),
        ("EXAMPLES", sections["examples"]),
        ("DESCRIPTION", sections["body"]),
    ):
        if lines:
            output.append(section_name)
            output.extend(f"  {line}" for line in lines)
            output.append("")

    return output


def _render_subcommands(
    all_commands: list,
    namespace: tuple[str, ...],
    short_help_fn,
) -> list[str]:
    """Render the SUBCOMMANDS section for a namespace."""
    subs = [
        c
        for c in all_commands
        if len(c.name) > len(namespace)
        and c.name[: len(namespace)] == namespace
        and not getattr(c, "hidden", False)
    ]
    if not subs:
        return []
    subs.sort(key=lambda c: c.name)
    out = ["SUBCOMMANDS"]
    for sub in subs:
        display = " ".join(sub.name)
        out.append(f"  {display:<28} {short_help_fn(sub.__doc__)}")
    out.append("")
    return out


# ---- Docstring parsing ----
#
# Command docstrings follow this convention (documented in _base.py):
#     One-line summary.
#
#     Usage: hop3 <path> ...
#
#     Examples:
#         hop3 <path> <example1>
#         hop3 <path> <example2>
#
# This parser recognizes "Usage:" and "Examples:" section headers
# (case-insensitive) and extracts their bodies. Anything else becomes
# the "body" content (displayed under "DESCRIPTION"). The first non-empty
# line is always the summary.
_SECTION_HEADERS = {
    "usage:": "usage",
    "examples:": "examples",
    "example:": "examples",  # singular form treated as examples
}


def _parse_docstring_sections(doc: str | None) -> dict:
    """Parse a docstring into summary / usage / examples / body sections.

    Returns a dict with keys: 'summary' (str), 'usage' (list[str]),
    'examples' (list[str]), 'body' (list[str]).
    """
    result: dict = {"summary": "", "usage": [], "examples": [], "body": []}
    if not doc:
        return result

    lines = doc.expandtabs().strip().split("\n")
    first_nonempty = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if first_nonempty is None:
        return result
    result["summary"] = lines[first_nonempty].strip()

    current = "body"
    for raw in lines[first_nonempty + 1 :]:
        stripped = raw.strip()
        if not stripped:
            continue
        new_section, tail = _classify_doc_line(stripped)
        if new_section is not None:
            current = new_section
            if tail:
                result[current].append(tail)
        else:
            result[current].append(stripped)

    return result


def _classify_doc_line(stripped: str) -> tuple[str | None, str]:
    """Classify a single stripped docstring line.

    Returns (section_name_or_None, tail). If the line is a recognized section
    header, section_name is set to the target section and tail contains any
    inline content after the header (empty string if the line was just the
    header like "Usage:"). Otherwise returns (None, "").
    """
    lower = stripped.lower()
    for header, section in _SECTION_HEADERS.items():
        if lower == header:
            return section, ""
        if lower.startswith(header):
            tail = stripped.split(":", 1)[1].strip()
            return section, tail
    return None, ""
