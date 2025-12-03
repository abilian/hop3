# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for --help flag handling and help output injection."""

from __future__ import annotations

from hop3_cli.main import handle_help_flags, inject_local_commands_into_help


def test_help_flags_basic():
    """Test basic --help flag handling."""
    # Just --help
    assert handle_help_flags(["--help"]) == ["help"]
    assert handle_help_flags(["-h"]) == ["help"]

    # Command with --help
    assert handle_help_flags(["run", "--help"]) == ["help", "run"]
    assert handle_help_flags(["run", "-h"]) == ["help", "run"]

    # Command with arguments and --help
    assert handle_help_flags(["run", "myapp", "--help"]) == ["help", "run"]
    assert handle_help_flags(["deploy", "app", "--help"]) == ["help", "deploy"]

    # No --help flag
    assert handle_help_flags(["run", "myapp"]) == ["run", "myapp"]
    assert handle_help_flags(["deploy"]) == ["deploy"]

    # Empty args
    assert handle_help_flags([]) == []


def test_help_flags_with_subcommands():
    """Test --help with subcommands."""
    assert handle_help_flags(["config:show", "--help"]) == ["help", "config:show"]
    assert handle_help_flags(["app:status", "-h"]) == ["help", "app:status"]


class TestInjectLocalCommandsIntoHelp:
    """Tests for inject_local_commands_into_help function."""

    def test_injects_local_commands_alphabetically(self):
        """Test that local commands are injected in alphabetical order."""
        # Simulate server help output (single text block with newlines, as server returns)
        server_help = [
            {
                "t": "text",
                "text": (
                    "USAGE\n"
                    "  $ hop <command>\n"
                    "\n"
                    "COMMANDS\n"
                    "  admin            Administrative commands.\n"
                    "  apps             List all applications.\n"
                    "  deploy           Deploy an application.\n"
                    "\n"
                    "Use 'hop help <command>' for details."
                ),
            }
        ]

        result = inject_local_commands_into_help(server_help)

        # Get the text content
        text = result[0].get("text", "")

        # Extract command names from the COMMANDS section
        commands = []
        in_commands = False
        for line in text.split("\n"):
            if line.strip() == "COMMANDS":
                in_commands = True
                continue
            if in_commands and line.startswith("  ") and line.strip():
                cmd = line.strip().split()[0]
                commands.append(cmd)
            elif in_commands and line.strip() and not line.startswith("  "):
                break

        # Verify local commands are present
        assert "init" in commands
        assert "login" in commands
        assert "settings" in commands

        # Verify alphabetical order is maintained
        assert commands == sorted(commands)

    def test_empty_result(self):
        """Test with empty result."""
        result = inject_local_commands_into_help([])
        assert result == []

    def test_no_commands_section(self):
        """Test when there's no COMMANDS section."""
        server_help = [
            {"t": "text", "text": "Some help text"},
        ]
        result = inject_local_commands_into_help(server_help)
        # Should return unchanged
        assert len(result) == 1
