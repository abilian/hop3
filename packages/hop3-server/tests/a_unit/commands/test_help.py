# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for help command."""

from __future__ import annotations

import pytest

from hop3.commands.help import HelpCmd, HelpCommandsCmd
from hop3.lib.console import verbosity_context
from hop3.lib.scanner import scan_package


@pytest.fixture(scope="module", autouse=True)
def register_all_commands():
    """Register all commands before running help tests."""
    scan_package("hop3.commands")


def test_help_overview():
    """Test help command without arguments shows overview of all commands."""
    cmd = HelpCmd()
    result = cmd.call()

    assert len(result) == 1
    assert result[0]["t"] == "text"
    text = result[0]["text"]

    # Check for usage section
    assert "USAGE" in text
    assert "$ hop <command> <args>" in text
    assert "$ hop help <command>" in text

    # Check for a category header (ADR 036 D4/D11 categorized layout)
    assert "UTILITIES" in text or "DAILY OPERATIONS" in text

    # Should at least contain the help command itself
    assert "help" in text


def test_help_detailed_for_specific_command():
    """Test help command with argument shows detailed help for that command."""
    cmd = HelpCmd()
    result = cmd.call("help")

    assert len(result) == 1
    assert result[0]["t"] == "text"
    text = result[0]["text"]

    # Per D11, detailed help starts with "hop <cmd> — <summary>" and then
    # structured sections (USAGE, EXAMPLES, etc.).
    assert "hop help" in text
    assert "Display useful help messages" in text
    assert "USAGE" in text


def test_help_for_unknown_command():
    """Test help command for unknown command shows error."""
    cmd = HelpCmd()
    result = cmd.call("nonexistent-command")

    # Should have error and help text
    assert len(result) == 2
    assert result[0]["t"] == "error"
    assert "Unknown command: nonexistent-command" in result[0]["text"]

    assert result[1]["t"] == "text"
    assert "hop help" in result[1]["text"]


def test_get_short_help_extracts_first_line():
    """Test _get_short_help extracts only the first line from docstring."""
    # Single line docstring
    short_help = HelpCmd._get_short_help("This is a one-liner.")
    assert short_help == "This is a one-liner."

    # Multi-line docstring - should only get first line
    multi_line = """Display useful help messages.

    This is additional information that should not appear
    in the overview. It's only shown when asking for detailed
    help about this specific command.
    """
    short_help = HelpCmd._get_short_help(multi_line)
    assert short_help == "Display useful help messages."

    # Empty docstring
    short_help = HelpCmd._get_short_help("")
    assert short_help == ""

    # None docstring
    short_help = HelpCmd._get_short_help(None)
    assert short_help == ""

    # Docstring with leading/trailing whitespace
    short_help = HelpCmd._get_short_help("  \n  First line here  \n\nSecond line\n  ")
    assert short_help == "First line here"


def test_help_overview_shows_only_short_descriptions():
    """Test that help overview shows only first line of each command's docstring."""
    cmd = HelpCmd()
    result = cmd.call()

    text = result[0]["text"]
    lines = text.split("\n")

    # Find any category section header (D4/D11 replaced the flat "COMMANDS"
    # section with task-oriented category headers).
    section_start = None
    for i, line in enumerate(lines):
        if line.strip() in {
            "DAILY OPERATIONS",
            "MANAGEMENT",
            "ADMINISTRATION",
            "UTILITIES",
            "OTHER",
        }:
            section_start = i
            break

    assert section_start is not None, "No category section found in help overview"

    # Check that command descriptions are single-line (no multi-line descriptions)
    # Each command line should be formatted as: "  command_name    description"
    command_lines = [
        line
        for line in lines[section_start + 1 :]
        if line.strip() and not line.startswith("USAGE")
    ]

    for line in command_lines:
        # Skip empty lines and section headers
        if not line.strip() or line.strip().startswith("$"):
            continue

        # Each command line should be reasonably short (not a paragraph)
        assert len(line) < 200, (
            f"Command description too long (possibly multi-line): {line}"
        )


def test_help_detailed_shows_full_docstring():
    """Test that detailed help shows the complete docstring content."""
    cmd = HelpCmd()

    # Test with the help command itself (which we know exists)
    result = cmd.call("help")

    # Should succeed (not show error)
    assert result[0]["t"] == "text"
    text = result[0]["text"]
    # D11 header: "hop <cmd> — <summary>"
    assert "hop help" in text
    # Should show the docstring content (summary + examples)
    assert "Display useful help messages" in text
    assert "EXAMPLES" in text


def test_help_all_shows_all_commands():
    """Test that 'hop help --all' shows all commands including subcommands."""
    cmd = HelpCmd()
    result = cmd.call("--all")

    assert len(result) == 1
    assert result[0]["t"] == "text"
    text = result[0]["text"]

    # Check for ALL COMMANDS section
    assert "ALL COMMANDS" in text

    # Should show subcommands (space-separated multi-token command names like
    # "auth login", "config set", etc.). Find any line listing such a command.
    lines = text.split("\n")
    has_subcommands = any(
        line.strip().startswith(("auth ", "config ", "app ", "backup ", "addons "))
        for line in lines
    )
    assert has_subcommands, "Expected subcommands to be shown with --all flag"


def test_help_all_flat_hints_at_verbose():
    """The terse `--all` index points users at the full `--all -v` document."""
    cmd = HelpCmd()
    text = cmd.call("--all")[0]["text"]
    assert "help --all -v" in text
    # Default (verbosity 1) stays the flat one-line index, not the full doc.
    assert "FULL HELP" not in text


def test_help_all_lists_aliases_with_alias_marker():
    """`hop help --all` lists aliases tagged [alias], pointing at the canonical."""
    cmd = HelpCmd()
    text = cmd.call("--all")[0]["text"]
    lines = [ln.strip() for ln in text.split("\n")]

    # A top-level alias: `logs` -> `app logs`.
    logs_alias = next((ln for ln in lines if ln.startswith("logs ")), None)
    assert logs_alias is not None, "expected the `logs` alias to be listed"
    assert "[alias]" in logs_alias
    assert "app logs" in logs_alias  # points at the canonical spelling

    # A namespaced rename alias: `domains` -> `domain`.
    domains_alias = next((ln for ln in lines if ln.startswith("domains ")), None)
    assert domains_alias is not None, "expected the `domains` alias to be listed"
    assert "[alias]" in domains_alias
    assert "domain" in domains_alias

    # The canonical still shows with its namespace marker, never [alias].
    app_logs = next((ln for ln in lines if ln.startswith("app logs ")), None)
    assert app_logs is not None
    assert "[app]" in app_logs


def test_help_all_verbose_aggregates_full_help():
    """`hop help --all -v` aggregates the full help for every command.

    Verbosity is forwarded by the client and applied as a context (see
    rpc.call); here we set it directly. The document must contain detailed
    pages — USAGE/EXAMPLES/SUBCOMMANDS — for many commands, not just a flat
    list of one-liners.
    """
    cmd = HelpCmd()
    with verbosity_context(2):
        result = cmd.call("--all")

    assert len(result) == 1
    text = result[0]["text"]

    assert "ALL COMMANDS — FULL HELP" in text
    # Detailed pages, repeated across the command set (not a single index).
    assert text.count("USAGE") > 5
    assert "SUBCOMMANDS" in text
    # Namespaced subcommands get their own page with a "Part of:" footer.
    assert "Part of: hop" in text
    # Spot-check that specific top-level and namespaced commands are present
    # as full-help headers.
    for header in ("hop deploy —", "hop env set —", "hop auth login —"):
        assert header in text, header


def test_help_default_shows_only_top_level():
    """Test that default help shows only top-level commands (no subcommands)."""
    cmd = HelpCmd()
    result = cmd.call()

    assert len(result) == 1
    text = result[0]["text"]

    # Should have hint about using help --all
    assert "hop help --all" in text

    # Commands section should not include subcommand lines
    # (lines starting with "  " followed by a name containing ":")
    lines = text.split("\n")
    # Find lines in COMMANDS section
    in_commands = False
    for line in lines:
        if "COMMANDS" in line:
            in_commands = True
            continue
        if in_commands and line.strip():
            # Skip hint lines
            if line.startswith("Use "):
                continue
            # Command lines start with "  " followed by command name
            if line.startswith("  ") and not line.strip().startswith("$"):
                # Extract command name (first word after leading spaces)
                parts = line.split()
                if parts:
                    cmd_name = parts[0]
                    assert ":" not in cmd_name, (
                        f"Subcommand '{cmd_name}' should not appear in default help"
                    )


def test_help_shows_subcommands_for_namespace():
    """Test that 'hop help <namespace>' shows subcommands."""
    cmd = HelpCmd()
    # 'auth' is a namespace command with subcommands like auth:login, etc.
    result = cmd.call("auth")

    assert len(result) == 1
    text = result[0]["text"]

    # Should show SUBCOMMANDS section
    assert "SUBCOMMANDS" in text

    # Should list auth subcommands (e.g., "auth login", "auth whoami")
    assert "auth " in text


def test_help_commands_returns_command_list():
    """Test that help:commands returns a list of all command names."""
    cmd = HelpCommandsCmd()
    result = cmd.call()

    assert len(result) == 1
    assert result[0]["t"] == "data"
    assert "data" in result[0]

    data = result[0]["data"]
    assert "commands" in data
    commands = data["commands"]

    # Should be a non-empty list of strings
    assert isinstance(commands, list)
    assert len(commands) > 0
    assert all(isinstance(c, str) for c in commands)

    # Should include some known commands. The list server-side uses canonical
    # names (ADR 036 D9); the `apps` form is a client-side alias, not a
    # canonical server command name.
    assert "help" in commands
    assert "app list" in commands

    # Should be sorted
    assert commands == sorted(commands)

    # Should not include hidden commands (e.g., git-hook)
    assert "git-hook" not in commands


def test_help_resolves_server_aliases():
    """`help <alias>` resolves server-side aliases instead of 'Unknown command'.

    Regression: `run` -> `app run` and `destroy` -> `app destroy` are aliases;
    their bare-form help used to report "Unknown command".
    """
    cmd = HelpCmd()
    for alias in (("run",), ("destroy",)):
        out = cmd._detailed_help(alias)
        assert "Unknown command" not in out[0]["text"], alias


def test_help_notes_alias_for_server_aliases():
    """`<alias> --help` states it's an alias for the canonical command."""
    cmd = HelpCmd()
    note = cmd._detailed_help(("config", "set"))[0]["text"]
    assert "`config set` is an alias for `env set`." in note
    # The canonical command does NOT get the alias note.
    canonical = cmd._detailed_help(("env", "set"))[0]["text"]
    assert "is an alias for" not in canonical
