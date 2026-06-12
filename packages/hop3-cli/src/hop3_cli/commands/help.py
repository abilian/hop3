# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Help flag handling and help output injection."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from .local import LOCAL_COMMANDS_INFO

if TYPE_CHECKING:
    from hop3_cli.config import Config

FEEDBACK_URL = "https://github.com/abilian/hop3/issues"


def handle_help_flags(args: list[str]) -> list[str]:
    """Convert --help/-h flags to help command invocations.

    Examples:
        ["--help"] -> ["help"]
        ["-h"] -> ["help"]
        ["run", "--help"] -> ["help", "run"]
        ["run", "-h"] -> ["help", "run"]
        ["run", "myapp", "--help"] -> ["help", "run", "myapp"]  # forward extra tokens
        ["config", "show", "--help"] -> ["help", "config", "show"]  # namespaced command

    With space-separated commands (ADR 036 D1), we forward all non-flag tokens
    before the first --help/-h so the server can show help for the full command path.

    Args:
        args: Command-line arguments

    Returns:
        Modified arguments with --help converted to help command
    """
    if not args:
        return args

    # Handle --version and -V flags
    if "--version" in args or "-V" in args:
        return ["version"]

    # Check if --help or -h is anywhere in the args
    if "--help" in args or "-h" in args:
        # Keep all tokens up to the first --help / -h, dropping any help flags.
        filtered: list[str] = []
        for arg in args:
            if arg in {"--help", "-h"}:
                break
            filtered.append(arg)
        # Also strip any later --help / -h (shouldn't happen, but be defensive)
        filtered = [a for a in filtered if a not in {"--help", "-h"}]

        if not filtered:
            # Just "--help" with no command -> show general help
            return ["help"]
        return ["help", *filtered]

    return args


def is_help_command(cli_args: list[str]) -> bool:
    """Check if this is a help command (with or without --all flag).

    Args:
        cli_args: Command-line arguments

    Returns:
        True if this is a help command that should have local commands injected
    """
    if not cli_args:
        return False
    # Match "help" or "help --all" but not "help <command>"
    if cli_args[0] != "help":
        return False
    # "help" alone or "help --all"
    return len(cli_args) == 1 or cli_args == ["help", "--all"]


def append_feedback_footer(result: list[dict]) -> list[dict]:
    """Append a feedback link to the end of the help output (ADR 036 D11, G7).

    The feedback URL is an ADR-mandated last line of the top-level help output
    so users always have a visible channel for reporting issues.
    """
    footer = f"\nReport issues: {FEEDBACK_URL}"
    return [*result, {"t": "text", "text": footer}]


def emit_status_line(config: Config) -> None:
    """Emit the dynamic 'Active context / Current app' line to stderr (D19).

    Per ADR 036 D11: bare `hop3 help` shows the active context and resolved
    default app so users can predict what app-scoped commands will target.
    This line goes to stderr (D19: dynamic/status output is stderr, not stdout)
    so it does not contaminate `hop3 help | grep ...` pipelines.
    """
    context_name = config.get_current_context_name()
    if not context_name:
        return  # No context active — no status line.

    default_app = config.get_default_app()
    app_part = (
        f"Current app: {default_app}"
        if default_app
        else "Current app: (none — set with `hop3 use <app>`)"
    )
    print(f"\nActive context: {context_name}      {app_part}", file=sys.stderr)


def append_local_commands_full_help(result: list[dict]) -> list[dict]:
    """Append the full help for client-side (local) commands.

    Used for `hop3 help --all -v`: the server renders the full help for every
    *server* command, but local commands (init, login, settings, ...) are
    handled entirely by the CLI and never reach the server. Appending their
    full help here keeps the aggregated document a complete reference of every
    command the user can run.
    """
    from .local.help_text import LOCAL_COMMAND_HELP  # noqa: PLC0415

    separator = "=" * 72
    lines = [
        separator,
        "",
        "CLIENT-SIDE (LOCAL) COMMANDS — FULL HELP",
        "",
        "These commands run in the CLI itself and are never sent to the server.",
        "",
    ]
    for name in sorted(LOCAL_COMMAND_HELP):
        lines.append(separator)
        lines.append("")
        lines.append(f"hop {name}")
        lines.append("")
        lines.append(LOCAL_COMMAND_HELP[name].rstrip())
        lines.append("")

    return [*result, {"t": "text", "text": "\n".join(lines).rstrip() + "\n"}]


def inject_local_commands_into_help(result: list[dict]) -> list[dict]:
    """Inject local CLI commands into the help output from the server.

    Local commands (init, login, settings) are handled by the CLI and don't
    exist on the server, so we add them to help output for discoverability.

    Args:
        result: The help response from the server

    Returns:
        Modified result with local commands injected alphabetically
    """
    modified_result = []
    for item in result:
        if item.get("t") != "text":
            modified_result.append(item)
            continue

        text = item.get("text", "")
        if "\n" in text and "COMMANDS" in text:
            new_text = _process_help_text_with_local_commands(text, LOCAL_COMMANDS_INFO)
            modified_result.append({"t": "text", "text": new_text})
        else:
            modified_result.append(item)

    return modified_result


def _collect_server_commands(lines: list[str]) -> set[str]:
    """Collect all command names from server output."""
    server_commands: set[str] = set()
    for line in lines:
        if _is_command_line(line):
            cmd_name = _get_command_name(line)
            if cmd_name:
                server_commands.add(cmd_name)
    return server_commands


def _insert_remaining_at_end(
    new_lines: list[str],
    remaining: list[str],
) -> None:
    """Insert remaining commands after the last command line."""
    insert_idx = len(new_lines)
    for i in range(len(new_lines) - 1, -1, -1):
        if _is_command_line(new_lines[i]):
            insert_idx = i + 1
            break
    for j, cmd_line in enumerate(remaining):
        new_lines.insert(insert_idx + j, cmd_line)


def _process_help_text_with_local_commands(
    text: str,
    local_commands: dict[str, str],
) -> str:
    """Process help text and inject local commands into COMMANDS section."""
    lines = text.split("\n")
    new_lines: list[str] = []
    in_commands_section = False
    is_all_commands = False

    # Align injected local commands to the server's name column so the markers
    # and descriptions line up (the server widths its column to the longest
    # command name; we mirror that here).
    name_width = _detect_command_name_width(lines)

    # Pre-collect server commands to avoid duplicates
    injected = _collect_server_commands(lines)

    for line in lines:
        stripped = line.strip()

        # Detect section headers
        if stripped in {"ALL COMMANDS", "COMMANDS"}:
            in_commands_section = True
            is_all_commands = stripped == "ALL COMMANDS"
            new_lines.append(line)
            continue

        # Detect leaving commands section
        if in_commands_section and stripped and not line.startswith("  "):
            new_lines.extend(
                _inject_remaining_commands(
                    local_commands, injected, is_all_commands, name_width
                )
            )
            in_commands_section = False

        # Inject local commands before current command if in section
        if in_commands_section and _is_command_line(line):
            current_cmd = _get_command_name(line)
            if current_cmd:
                new_lines.extend(
                    _inject_commands_before(
                        current_cmd,
                        local_commands,
                        injected,
                        is_all_commands,
                        name_width,
                    )
                )

        new_lines.append(line)

    # Handle remaining commands at end of section
    if in_commands_section:
        remaining = _inject_remaining_commands(
            local_commands, injected, is_all_commands, name_width
        )
        if remaining:
            _insert_remaining_at_end(new_lines, remaining)

    return "\n".join(new_lines)


def _detect_command_name_width(lines: list[str], default: int = 24) -> int:
    """Infer the server's name-column width from its `--all` command lines.

    Server `--all` lines look like ``  <name padded to W> [marker]  <help>``.
    The marker is the first ``[`` on the line (command names never contain
    brackets), so ``W = index_of_first_bracket - 3`` (two leading spaces, the
    name, then one space). Falls back to ``default`` when no marker line is
    found (e.g. the bare grouped view, or a server that predates dynamic
    widths).
    """
    for line in lines:
        if not line.startswith("  "):
            continue
        bracket = line.find("[")
        if bracket > 3:
            return bracket - 3
    return default


def _inject_remaining_commands(
    local_commands: dict[str, str],
    injected: set[str],
    is_all_commands: bool = False,
    name_width: int = 24,
) -> list[str]:
    """Return all local commands not yet injected."""
    lines = []
    for cmd in sorted(local_commands.keys()):
        if cmd not in injected:
            lines.append(
                _format_help_command(
                    cmd, local_commands[cmd], is_all_commands, name_width
                )
            )
            injected.add(cmd)
    return lines


def _is_command_line(line: str) -> bool:
    """Check if a line is a command entry (indented, non-empty)."""
    return line.startswith("  ") and bool(line.strip())


def _get_command_name(line: str) -> str | None:
    """Extract command name from a help line."""
    parts = line.strip().split(None, 1)
    return parts[0] if parts else None


def _inject_commands_before(
    current_cmd: str,
    local_commands: dict[str, str],
    injected: set[str],
    is_all_commands: bool = False,
    name_width: int = 24,
) -> list[str]:
    """Return local commands that should appear before current_cmd alphabetically."""
    lines = []
    for cmd in sorted(local_commands.keys()):
        if cmd not in injected and cmd < current_cmd:
            lines.append(
                _format_help_command(
                    cmd, local_commands[cmd], is_all_commands, name_width
                )
            )
            injected.add(cmd)
    return lines


def _format_help_command(
    name: str,
    description: str,
    wide: bool = False,
    name_width: int = 24,
) -> str:
    """Format a command entry for help output.

    Args:
        name: Command name
        description: Command description
        wide: If True, this is the `--all` view: emit the same
            ``name  [marker]  help`` columns the server uses, tagging local
            commands with a ``[local]`` marker so they line up with server
            commands. Otherwise use the narrow grouped-view layout.
        name_width: Width of the name column in `--all` mode (matched to the
            server's column so markers align).
    """
    if wide:
        return f"  {name:<{name_width}} {'[local]':<10} {description}"
    return f"  {name:<16} {description}"
