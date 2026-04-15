# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for confirmation flow in main.py."""

from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import patch

from hop3_cli.main import (
    confirm_destructive_action,
    is_destructive_command,
)
from hop3_cli.ui.rich_printer import RichPrinter


def test_is_destructive_command_app_destroy():
    """Test detection of app:destroy and destroy commands."""
    assert is_destructive_command(["app", "destroy", "my-app"]) is True
    assert is_destructive_command(["destroy", "my-app"]) is True
    assert is_destructive_command(["app", "destroy"]) is True


def test_is_destructive_command_backup_delete():
    """Test detection of backup:delete command."""
    assert is_destructive_command(["backup", "destroy", "backup-id"]) is True
    assert is_destructive_command(["backup", "destroy"]) is True


def test_is_destructive_command_addon_destroy():
    """Test detection of addon destroy command."""
    assert is_destructive_command(["addon", "destroy", "postgres"]) is True
    assert is_destructive_command(["addon", "destroy"]) is True


def test_is_destructive_command_safe_commands():
    """Test that safe commands are not detected as destructive."""
    assert is_destructive_command(["deploy", "my-app"]) is False
    assert is_destructive_command(["apps"]) is False
    assert is_destructive_command(["app", "status", "my-app"]) is False
    assert is_destructive_command(["backup", "list"]) is False
    assert is_destructive_command(["help"]) is False


def test_is_destructive_command_empty():
    """Test with empty command list."""
    assert is_destructive_command([]) is False


def test_confirm_destructive_action_app_destroy_confirmed():
    """Test app:destroy confirmation when user types correct app name."""
    printer = RichPrinter()

    with patch("builtins.input", return_value="my-app"):
        result = confirm_destructive_action(["app", "destroy", "my-app"], printer)
        assert result is True


def test_confirm_destructive_action_app_destroy_cancelled():
    """Test app:destroy confirmation when user types incorrect app name."""
    printer = RichPrinter()

    with patch("builtins.input", return_value="wrong-app"):
        result = confirm_destructive_action(["app", "destroy", "my-app"], printer)
        assert result is False


def test_confirm_destructive_action_app_destroy_no_arg():
    """Test app:destroy with no app name (let server handle error)."""
    printer = RichPrinter()

    # When no app name provided, should auto-confirm (server will show error)
    result = confirm_destructive_action(["app", "destroy"], printer)
    assert result is True


def test_confirm_destructive_action_backup_delete_confirmed():
    """Test backup:delete confirmation when user confirms."""
    printer = RichPrinter()

    with patch("builtins.input", return_value="y"):
        result = confirm_destructive_action(["backup", "destroy", "backup-123"], printer)
        assert result is True


def test_confirm_destructive_action_backup_delete_cancelled():
    """Test backup:delete confirmation when user cancels."""
    printer = RichPrinter()

    with patch("builtins.input", return_value="n"):
        result = confirm_destructive_action(["backup", "destroy", "backup-123"], printer)
        assert result is False


def test_confirm_destructive_action_addon_destroy_confirmed():
    """Test addon destroy confirmation when user types correct service name."""
    printer = RichPrinter()

    with patch("builtins.input", return_value="postgres"):
        result = confirm_destructive_action(["addon", "destroy", "postgres"], printer)
        assert result is True


def test_confirm_destructive_action_addon_destroy_cancelled():
    """Test addon destroy confirmation when user types incorrect service name."""
    printer = RichPrinter()

    with patch("builtins.input", return_value="mysql"):
        result = confirm_destructive_action(["addon", "destroy", "postgres"], printer)
        assert result is False


def test_confirm_destructive_action_json_mode():
    """Test that JSON mode auto-confirms all destructive actions."""
    printer = RichPrinter(json_output=True)

    # All destructive commands should auto-confirm in JSON mode
    assert confirm_destructive_action(["app", "destroy", "my-app"], printer) is True
    assert confirm_destructive_action(["backup", "destroy", "backup-123"], printer) is True
    assert confirm_destructive_action(["addon", "destroy", "postgres"], printer) is True


def test_confirm_destructive_action_destroy_alias():
    """Test that 'destroy' alias works like 'app destroy'."""
    printer = RichPrinter()

    with patch("builtins.input", return_value="my-app"):
        result = confirm_destructive_action(["destroy", "my-app"], printer)
        assert result is True

    with patch("builtins.input", return_value="wrong"):
        result = confirm_destructive_action(["destroy", "my-app"], printer)
        assert result is False


def test_confirm_destructive_action_shows_warnings():
    """Test that warnings are shown to stderr."""
    printer = RichPrinter()

    stderr_capture = StringIO()
    with (
        patch.object(sys, "stderr", stderr_capture),
        patch("builtins.input", return_value="my-app"),
    ):
        confirm_destructive_action(["app", "destroy", "my-app"], printer)

    output = stderr_capture.getvalue()
    assert "⚠  WARNING: DESTRUCTIVE ACTION" in output
    assert "app 'my-app'" in output
    assert "This action CANNOT be undone!" in output


def test_confirm_destructive_action_app_destroy_warning_details():
    """Test app:destroy shows specific warning details."""
    printer = RichPrinter()

    stderr_capture = StringIO()
    with (
        patch.object(sys, "stderr", stderr_capture),
        patch("builtins.input", return_value="my-app"),
    ):
        confirm_destructive_action(["app", "destroy", "my-app"], printer)

    output = stderr_capture.getvalue()
    assert "All files, data, and configuration will be permanently deleted." in output


def test_confirm_destructive_action_backup_delete_warning_details():
    """Test backup:delete shows specific warning details."""
    printer = RichPrinter()

    stderr_capture = StringIO()
    with (
        patch.object(sys, "stderr", stderr_capture),
        patch("builtins.input", return_value="y"),
    ):
        confirm_destructive_action(["backup", "destroy", "backup-123"], printer)

    output = stderr_capture.getvalue()
    assert "backup 'backup-123'" in output
    assert "This backup cannot be recovered once deleted." in output


def test_confirm_destructive_action_addon_destroy_warning_details():
    """Test addon destroy shows specific warning details."""
    printer = RichPrinter()

    stderr_capture = StringIO()
    with (
        patch.object(sys, "stderr", stderr_capture),
        patch("builtins.input", return_value="postgres"),
    ):
        confirm_destructive_action(["addon", "destroy", "postgres"], printer)

    output = stderr_capture.getvalue()
    assert "service 'postgres'" in output
    assert "All data in this service will be permanently deleted." in output


def test_confirm_destructive_action_keyboard_interrupt():
    """Test that Ctrl+C during confirmation cancels the action."""
    printer = RichPrinter()

    with patch("builtins.input", side_effect=KeyboardInterrupt):
        result = confirm_destructive_action(["app", "destroy", "my-app"], printer)
        assert result is False


def test_confirm_destructive_action_eof():
    """Test that Ctrl+D during confirmation cancels the action."""
    printer = RichPrinter()

    with patch("builtins.input", side_effect=EOFError):
        result = confirm_destructive_action(["app", "destroy", "my-app"], printer)
        assert result is False
