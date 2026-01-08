# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Help flag handling and help output injection."""

from __future__ import annotations

from .local import LOCAL_COMMANDS_INFO


def handle_help_flags(args: list[str]) -> list[str]:
    """Convert --help/-h flags to help command invocations.

    Examples:
        ["--help"] -> ["help"]
        ["-h"] -> ["help"]
        ["run", "--help"] -> ["help", "run"]
        ["run", "-h"] -> ["help", "run"]
        ["run", "myapp", "--help"] -> ["help", "run"]  # help for run, not run with --help

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
        # Remove --help and -h from args
        filtered_args = [arg for arg in args if arg not in {"--help", "-h"}]

        if not filtered_args:
            # Just "--help" with no command -> show general help
            return ["help"]
        # "command --help" -> "help command"
        # Only use the first argument as the command name
        return ["help", filtered_args[0]]

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


def _process_help_text_with_local_commands(
    text: str,
    local_commands: dict[str, str],
) -> str:
    """Process help text and inject local commands into COMMANDS section."""
    lines = text.split("\n")
    new_lines = []
    in_commands_section = False
    injected: set[str] = set()

    for line in lines:
        if line.strip() in {"COMMANDS", "ALL COMMANDS"}:
            in_commands_section = True
            new_lines.append(line)
            continue

        if in_commands_section and line.strip() and not line.startswith("  "):
            # Leaving COMMANDS section - inject remaining commands first
            new_lines.extend(_inject_remaining_commands(local_commands, injected))
            in_commands_section = False

        if in_commands_section and _is_command_line(line):
            current_cmd = _get_command_name(line)
            if current_cmd:
                new_lines.extend(
                    _inject_commands_before(current_cmd, local_commands, injected)
                )

        new_lines.append(line)

    # If still in commands section at end, inject remaining
    if in_commands_section:
        remaining = _inject_remaining_commands(local_commands, injected)
        if remaining:
            # Insert after last command line
            insert_idx = len(new_lines)
            for i in range(len(new_lines) - 1, -1, -1):
                if _is_command_line(new_lines[i]):
                    insert_idx = i + 1
                    break
            for j, cmd_line in enumerate(remaining):
                new_lines.insert(insert_idx + j, cmd_line)

    return "\n".join(new_lines)


def _inject_remaining_commands(
    local_commands: dict[str, str],
    injected: set[str],
) -> list[str]:
    """Return all local commands not yet injected."""
    lines = []
    for cmd in sorted(local_commands.keys()):
        if cmd not in injected:
            lines.append(_format_help_command(cmd, local_commands[cmd]))
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
) -> list[str]:
    """Return local commands that should appear before current_cmd alphabetically."""
    lines = []
    for cmd in sorted(local_commands.keys()):
        if cmd not in injected and cmd < current_cmd:
            lines.append(_format_help_command(cmd, local_commands[cmd]))
            injected.add(cmd)
    return lines


def _format_help_command(name: str, description: str) -> str:
    """Format a command entry for help output."""
    return f"  {name:16} {description}"
