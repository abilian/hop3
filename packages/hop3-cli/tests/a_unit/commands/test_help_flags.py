# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for --help flag handling and help output injection."""

from __future__ import annotations

from hop3_cli.commands.help import (
    append_local_commands_full_help,
    handle_help_flags,
    inject_local_commands_into_help,
    is_help_command,
)
from hop3_cli.main import requires_authentication
from hop3_cli.rpc.responses import handle_ok_response
from hop3_cli.ui import RichPrinter
from stubs import StubConfig


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
    # `auth login` / `auth logout` are handled locally and never reach this RPC
    # gate; `auth get-token` is the public no-auth command behind login.
    assert requires_authentication(["auth", "get-token"]) is False
    assert requires_authentication(["auth", "get-token", "user", "pass"]) is False
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


class TestAppendLocalCommandsFullHelp:
    """Tests for the `hop3 help --all -v` local-command aggregation."""

    def test_appends_full_local_help_block(self):
        """Full help (not one-liners) for local commands is appended."""
        result = [{"t": "text", "text": "ALL COMMANDS — FULL HELP\nhop deploy — x"}]
        out = append_local_commands_full_help(result)

        # Original server document is preserved untouched as the first item.
        assert out[0] == {
            "t": "text",
            "text": "ALL COMMANDS — FULL HELP\nhop deploy — x",
        }

        text = out[-1]["text"]
        assert "CLIENT-SIDE (LOCAL) COMMANDS" in text
        # Full help bodies, not just one-line descriptions.
        assert "Usage: hop3 init --ssh" in text
        assert "Usage: hop3 settings" in text
        assert "Usage: hop3 completion" in text
        # Every local command with centralized help appears.
        for name in ("init", "login", "settings", "context", "use", "aliases"):
            assert f"hop {name}" in text


def test_verbose_help_all_appends_full_local_help(capsys):
    """`hop3 help --all -v` appends full local help, not one-liners."""
    server_doc = [
        {"t": "text", "text": "ALL COMMANDS — FULL HELP\nhop deploy — Deploy."}
    ]
    printer = RichPrinter(verbose=True)

    handle_ok_response(server_doc, ["help", "--all"], StubConfig(), printer)

    out = capsys.readouterr().out
    assert "CLIENT-SIDE (LOCAL) COMMANDS" in out
    assert "Usage: hop3 init --ssh" in out
    # Feedback footer (G7) still appended.
    assert "Report issues:" in out


def test_nonverbose_help_all_keeps_oneliner_injection(capsys):
    """Plain `hop3 help --all` keeps the flat one-liner injection (unchanged)."""
    server_doc = [
        {
            "t": "text",
            "text": (
                "USAGE\n  $ hop <command>\n\nALL COMMANDS\n"
                "  apps             List all applications.\n"
            ),
        }
    ]
    printer = RichPrinter(verbose=False)

    handle_ok_response(server_doc, ["help", "--all"], StubConfig(), printer)

    out = capsys.readouterr().out
    # No full-help appendix in the terse mode.
    assert "CLIENT-SIDE (LOCAL) COMMANDS" not in out
    # Local commands still injected as one-liners.
    assert "init" in out
    assert "settings" in out


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

    def test_all_commands_local_markers_align_with_server(self):
        """
        Injected local commands get a [local] marker aligned to the server's.

        The server widths its name column to the longest command name; the
        client must mirror that width so every marker column lines up.
        """
        # Server output with a deliberately long name -> wide name column.
        server_help = [
            {
                "t": "text",
                "text": (
                    "ALL COMMANDS\n"
                    "  admin reencrypt-credentials [admin]    Rewrite credentials.\n"
                    "  app                         [top]      Manage apps.\n"
                    "  zzz                         [top]      Last server command.\n"
                ),
            }
        ]

        text = inject_local_commands_into_help(server_help)[0]["text"]
        lines = [ln for ln in text.split("\n") if "[" in ln and ln.startswith("  ")]

        # Local commands carry a [local] marker.
        local_lines = [ln for ln in lines if "[local]" in ln]
        assert local_lines, "expected injected local commands with [local] marker"
        assert any("init" in ln for ln in local_lines)

        # Every marker starts at the same column (server and local alike).
        marker_columns = {ln.index("[") for ln in lines}
        assert len(marker_columns) == 1, (
            f"markers not aligned; columns seen: {sorted(marker_columns)}"
        )

    def test_all_commands_injects_core_aliases_with_alias_marker(self):
        """`--all` lists client-side core aliases tagged [alias] -> canonical."""
        server_help = [
            {
                "t": "text",
                "text": (
                    "ALL COMMANDS\n"
                    "  app list    [app]     List all applications.\n"
                    "  auth whoami [auth]    Show the current user.\n"
                ),
            }
        ]
        text = inject_local_commands_into_help(server_help)[0]["text"]
        lines = [ln.strip() for ln in text.split("\n")]

        apps = next((ln for ln in lines if ln.startswith("apps ")), None)
        assert apps is not None
        assert "[alias]" in apps
        assert "app list" in apps  # points at the canonical

        whoami = next((ln for ln in lines if ln.startswith("whoami ")), None)
        assert whoami is not None
        assert "[alias]" in whoami
        assert "auth whoami" in whoami

    def test_grouped_view_does_not_inject_core_aliases(self):
        """The narrow grouped view (`hop help`) must not list aliases."""
        server_help = [
            {
                "t": "text",
                "text": ("COMMANDS\n  app      Manage apps.\n  deploy   Deploy.\n"),
            }
        ]
        text = inject_local_commands_into_help(server_help)[0]["text"]
        # No [alias] marker, and no core-alias names leak into the grouped view.
        assert "[alias]" not in text
        names = [
            ln.strip().split()[0] for ln in text.split("\n") if ln.startswith("  ")
        ]
        assert "whoami" not in names
        assert "apps" not in names

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
