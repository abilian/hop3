# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for help command."""

from __future__ import annotations

from hop3.commands.help import HelpCmd


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

    # Check for commands section
    assert "COMMANDS" in text

    # Should at least contain the help command itself
    assert "help" in text


def test_help_detailed_for_specific_command():
    """Test help command with argument shows detailed help for that command."""
    cmd = HelpCmd()
    result = cmd.call("help")

    assert len(result) == 1
    assert result[0]["t"] == "text"
    text = result[0]["text"]

    # Check for command-specific header
    assert "COMMAND: help" in text

    # Should show full docstring
    assert "Display useful help messages" in text


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

    # Find the COMMANDS section
    commands_start = None
    for i, line in enumerate(lines):
        if "COMMANDS" in line:
            commands_start = i
            break

    assert commands_start is not None, "COMMANDS section not found"

    # Check that command descriptions are single-line (no multi-line descriptions)
    # Each command line should be formatted as: "  command_name    description"
    command_lines = [
        line
        for line in lines[commands_start + 1 :]
        if line.strip() and not line.startswith("USAGE")
    ]

    for line in command_lines:
        # Skip empty lines and section headers
        if not line.strip() or line.strip().startswith("$"):
            continue

        # Each command line should be reasonably short (not a paragraph)
        # A good heuristic is that one-line descriptions should be under 150 chars
        assert len(line) < 200, (
            f"Command description too long (possibly multi-line): {line}"
        )


def test_help_detailed_shows_full_docstring():
    """Test that detailed help shows the complete docstring."""
    cmd = HelpCmd()

    # Test with the help command itself (which we know exists)
    result = cmd.call("help")

    # Should succeed (not show error)
    assert result[0]["t"] == "text"
    text = result[0]["text"]
    # Should have the command header
    assert "COMMAND: help" in text
    # Should show the docstring
    assert "Display useful help messages" in text
