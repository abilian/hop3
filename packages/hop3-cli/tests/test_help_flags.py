# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for --help flag handling and help output injection."""

from __future__ import annotations

from hop3_cli.commands.help import (
    handle_help_flags,
    inject_local_commands_into_help,
    is_help_command,
)
from hop3_cli.main import requires_authentication


def test_help_flags_basic():
    """Test basic --help flag handling."""
    # Just --help
    assert handle_help_flags(["--help"]) == ["help"]
    assert handle_help_flags(["-h"]) == ["help"]

    # Command with --help
    assert handle_help_flags(["run", "--help"]) == ["help", "run"]
    assert handle_help_flags(["run", "-h"]) == ["help", "run"]

    # Command with arguments and --help: forward extra tokens so the server
    # can show the most specific help (longest-prefix match). `hop3 config show
    # myapp --help` wants `help config show`; `hop3 run myapp --help` will show
    # help for `run` via longest-prefix fallback.
    assert handle_help_flags(["run", "myapp", "--help"]) == ["help", "run", "myapp"]
    assert handle_help_flags(["deploy", "app", "--help"]) == ["help", "deploy", "app"]

    # No --help flag
    assert handle_help_flags(["run", "myapp"]) == ["run", "myapp"]
    assert handle_help_flags(["deploy"]) == ["deploy"]

    # Empty args
    assert handle_help_flags([]) == []


def test_version_flags():
    """Test --version flag handling."""
    # Just --version
    assert handle_help_flags(["--version"]) == ["version"]
    assert handle_help_flags(["-V"]) == ["version"]

    # Command with --version (version takes precedence)
    assert handle_help_flags(["run", "--version"]) == ["version"]
    assert handle_help_flags(["deploy", "-V"]) == ["version"]


def test_requires_authentication():
    """Test requires_authentication function."""
    # Commands that DON'T require authentication
    assert requires_authentication(["help"]) is False
    assert requires_authentication(["help", "deploy"]) is False
    assert requires_authentication(["help", "--all"]) is False
    assert requires_authentication(["version"]) is False
    assert requires_authentication(["auth"]) is False
    assert requires_authentication(["auth", "login"]) is False
    assert requires_authentication(["auth", "login", "user", "pass"]) is False
    assert requires_authentication(["auth", "register"]) is False

    # Commands that DO require authentication
    assert requires_authentication(["apps"]) is True
    assert requires_authentication(["deploy", "myapp"]) is True
    assert requires_authentication(["app", "status", "myapp"]) is True
    assert requires_authentication(["config", "set", "KEY", "value"]) is True
    assert requires_authentication(["auth", "whoami"]) is True  # whoami requires auth

    # Empty args
    assert requires_authentication([]) is False


def test_help_flags_with_subcommands():
    """Test --help with subcommands."""
    assert handle_help_flags(["config", "show", "--help"]) == ["help", "config", "show"]
    assert handle_help_flags(["app", "status", "-h"]) == ["help", "app", "status"]


def test_is_help_command():
    """Test is_help_command helper function."""
    # Plain help command
    assert is_help_command(["help"]) is True
    # Help with --all flag
    assert is_help_command(["help", "--all"]) is True
    # Help for specific command (should NOT inject local commands)
    assert is_help_command(["help", "deploy"]) is False
    assert is_help_command(["help", "config", "set"]) is False
    # Not a help command
    assert is_help_command(["deploy"]) is False
    assert is_help_command(["apps"]) is False
    # Empty args
    assert is_help_command([]) is False


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

    def test_injects_into_all_commands_section(self):
        """Test that local commands are injected into ALL COMMANDS section (--all flag)."""
        # Simulate server help --all output
        server_help = [
            {
                "t": "text",
                "text": (
                    "USAGE\n"
                    "  $ hop <command>\n"
                    "\n"
                    "ALL COMMANDS\n"
                    "  admin            Administrative commands.\n"
                    "  admin:users      Manage users.\n"
                    "  apps             List all applications.\n"
                    "  deploy           Deploy an application.\n"
                ),
            }
        ]

        result = inject_local_commands_into_help(server_help)

        # Get the text content
        text = result[0].get("text", "")

        # Extract command names from the ALL COMMANDS section
        commands = []
        in_commands = False
        for line in text.split("\n"):
            if line.strip() == "ALL COMMANDS":
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
