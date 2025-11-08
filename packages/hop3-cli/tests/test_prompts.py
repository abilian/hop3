# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for interactive prompts."""

from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import patch

from hop3_cli.prompts import confirm, show_destructive_warning, type_to_confirm


def test_confirm_yes():
    """Test confirm() with 'yes' responses."""
    # Full 'yes'
    with patch("builtins.input", return_value="yes"):
        assert confirm("Delete file?") is True

    # Short 'y'
    with patch("builtins.input", return_value="y"):
        assert confirm("Delete file?") is True

    # Uppercase 'Y'
    with patch("builtins.input", return_value="Y"):
        assert confirm("Delete file?") is True

    # Uppercase 'YES'
    with patch("builtins.input", return_value="YES"):
        assert confirm("Delete file?") is True

    # With whitespace
    with patch("builtins.input", return_value="  yes  "):
        assert confirm("Delete file?") is True


def test_confirm_no():
    """Test confirm() with 'no' responses."""
    # Full 'no'
    with patch("builtins.input", return_value="no"):
        assert confirm("Delete file?") is False

    # Short 'n'
    with patch("builtins.input", return_value="n"):
        assert confirm("Delete file?") is False

    # Anything else
    with patch("builtins.input", return_value="maybe"):
        assert confirm("Delete file?") is False

    with patch("builtins.input", return_value="x"):
        assert confirm("Delete file?") is False


def test_confirm_default():
    """Test confirm() default behavior with empty input."""
    # Default is False
    with patch("builtins.input", return_value=""):
        assert confirm("Delete file?", default=False) is False

    # Default is True
    with patch("builtins.input", return_value=""):
        assert confirm("Delete file?", default=True) is True


def test_confirm_keyboard_interrupt():
    """Test confirm() with Ctrl+C (KeyboardInterrupt)."""
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        result = confirm("Delete file?")
        assert result is False


def test_confirm_eof():
    """Test confirm() with Ctrl+D (EOFError)."""
    with patch("builtins.input", side_effect=EOFError):
        result = confirm("Delete file?")
        assert result is False


def test_type_to_confirm_correct():
    """Test type_to_confirm() with correct input."""
    with patch("builtins.input", return_value="my-app"):
        assert type_to_confirm("Type 'my-app' to confirm:", "my-app") is True

    # Case sensitive
    with patch("builtins.input", return_value="My-App"):
        assert type_to_confirm("Type 'my-app' to confirm:", "my-app") is False


def test_type_to_confirm_incorrect():
    """Test type_to_confirm() with incorrect input."""
    with patch("builtins.input", return_value="wrong-app"):
        result = type_to_confirm("Type 'my-app' to confirm:", "my-app")
        assert result is False

    # Empty string
    with patch("builtins.input", return_value=""):
        result = type_to_confirm("Type 'my-app' to confirm:", "my-app")
        assert result is False

    # Partial match
    with patch("builtins.input", return_value="my"):
        result = type_to_confirm("Type 'my-app' to confirm:", "my-app")
        assert result is False


def test_type_to_confirm_with_whitespace():
    """Test type_to_confirm() strips whitespace."""
    # Leading/trailing whitespace should be stripped
    with patch("builtins.input", return_value="  my-app  "):
        assert type_to_confirm("Type 'my-app' to confirm:", "my-app") is True

    # But internal whitespace matters
    with patch("builtins.input", return_value="my app"):
        assert type_to_confirm("Type 'my-app' to confirm:", "my-app") is False


def test_type_to_confirm_keyboard_interrupt():
    """Test type_to_confirm() with Ctrl+C."""
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        result = type_to_confirm("Type 'my-app' to confirm:", "my-app")
        assert result is False


def test_type_to_confirm_eof():
    """Test type_to_confirm() with Ctrl+D."""
    with patch("builtins.input", side_effect=EOFError):
        result = type_to_confirm("Type 'my-app' to confirm:", "my-app")
        assert result is False


def test_show_destructive_warning_basic():
    """Test show_destructive_warning() output."""
    # Capture stderr output
    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        show_destructive_warning("destroy", "app 'my-app'")

    output = stderr_capture.getvalue()
    assert "⚠  WARNING: DESTRUCTIVE ACTION" in output
    assert "This will permanently destroy app 'my-app'." in output
    assert "This action CANNOT be undone!" in output


def test_show_destructive_warning_with_details():
    """Test show_destructive_warning() with additional details."""
    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        show_destructive_warning(
            "destroy",
            "app 'my-app'",
            "All files, data, and configuration will be permanently deleted.",
        )

    output = stderr_capture.getvalue()
    assert "⚠  WARNING: DESTRUCTIVE ACTION" in output
    assert "This will permanently destroy app 'my-app'." in output
    assert "All files, data, and configuration will be permanently deleted." in output
    assert "This action CANNOT be undone!" in output


def test_show_destructive_warning_no_details():
    """Test show_destructive_warning() without details."""
    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        show_destructive_warning("delete", "backup '123'", "")

    output = stderr_capture.getvalue()
    assert "⚠  WARNING: DESTRUCTIVE ACTION" in output
    assert "This will permanently delete backup '123'." in output
    assert "This action CANNOT be undone!" in output
    # When no details, should have fewer lines than with details
    # Format: \n, WARNING, \n, action, \n, cannot undo, \n = 7 newlines
    assert output.count("\n") == 7


def test_show_destructive_warning_different_commands():
    """Test show_destructive_warning() with different command types."""
    # destroy command
    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        show_destructive_warning("destroy", "service 'postgres'")
    assert "permanently destroy service 'postgres'" in stderr_capture.getvalue()

    # delete command
    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        show_destructive_warning("delete", "backup 'abc123'")
    assert "permanently delete backup 'abc123'" in stderr_capture.getvalue()

    # remove command
    stderr_capture = StringIO()
    with patch.object(sys, "stderr", stderr_capture):
        show_destructive_warning("remove", "all data")
    assert "permanently remove all data" in stderr_capture.getvalue()
