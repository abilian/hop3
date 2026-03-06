# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for command execution utilities."""

from __future__ import annotations

import subprocess
from contextlib import suppress

import pytest

from hop3.lib.util import (
    CommandError,
    CommandFailedError,
    CommandNotFoundError,
    CommandTimeoutError,
    run_command,
    try_commands,
)


class TestCommandError:
    """Tests for CommandError exception hierarchy."""

    def test_command_error_message(self):
        """CommandError formats message with command string."""
        err = CommandError(["foo", "bar"], "something went wrong")
        assert str(err) == "foo bar: something went wrong"
        assert err.cmd == ["foo", "bar"]
        assert err.cmd_str == "foo bar"
        assert err.message == "something went wrong"

    def test_command_not_found_error(self):
        """CommandNotFoundError includes the command name."""
        err = CommandNotFoundError(["nonexistent", "--flag"])
        assert "command 'nonexistent' not found" in str(err)
        assert err.cmd == ["nonexistent", "--flag"]

    def test_command_timeout_error(self):
        """CommandTimeoutError includes the timeout value."""
        err = CommandTimeoutError(["slow", "command"], timeout=30)
        assert "timed out after 30s" in str(err)
        assert err.timeout == 30

    def test_command_failed_error_without_stderr(self):
        """CommandFailedError shows exit code."""
        err = CommandFailedError(["failing", "cmd"], returncode=42)
        assert "exited with code 42" in str(err)
        assert err.returncode == 42
        assert err.stderr == ""

    def test_command_failed_error_with_stderr(self):
        """CommandFailedError includes stderr when available."""
        err = CommandFailedError(
            ["failing", "cmd"], returncode=1, stderr="permission denied"
        )
        assert "exited with code 1" in str(err)
        assert "permission denied" in str(err)
        assert err.stderr == "permission denied"

    def test_exception_hierarchy(self):
        """All specific errors inherit from CommandError."""
        assert issubclass(CommandNotFoundError, CommandError)
        assert issubclass(CommandTimeoutError, CommandError)
        assert issubclass(CommandFailedError, CommandError)

        # Can catch all with CommandError
        with pytest.raises(CommandError):
            raise CommandNotFoundError(["test"])

        with pytest.raises(CommandError):
            raise CommandTimeoutError(["test"], 10)

        with pytest.raises(CommandError):
            raise CommandFailedError(["test"], 1)


class TestRunCommand:
    """Tests for run_command function."""

    def test_successful_command(self):
        """run_command returns CompletedProcess on success."""
        result = run_command(["echo", "hello"])
        assert isinstance(result, subprocess.CompletedProcess)
        assert result.returncode == 0

    def test_command_not_found(self):
        """run_command raises CommandNotFoundError for missing commands."""
        with pytest.raises(CommandNotFoundError) as exc_info:
            run_command(["nonexistent_command_xyz_123"])

        assert "command 'nonexistent_command_xyz_123' not found" in str(exc_info.value)

    def test_command_failure(self):
        """run_command raises CommandFailedError on non-zero exit."""
        with pytest.raises(CommandFailedError) as exc_info:
            run_command(["false"])  # 'false' always exits with code 1

        assert exc_info.value.returncode == 1
        assert "exited with code 1" in str(exc_info.value)

    def test_command_failure_with_stderr(self):
        """run_command captures stderr in the exception."""
        with pytest.raises(CommandFailedError) as exc_info:
            run_command(["sh", "-c", "echo error message >&2; exit 2"])

        assert exc_info.value.returncode == 2
        assert "error message" in exc_info.value.stderr

    def test_command_timeout(self):
        """run_command raises CommandTimeoutError when command takes too long."""
        with pytest.raises(CommandTimeoutError) as exc_info:
            run_command(["sleep", "10"], timeout=1)

        assert "timed out after 1s" in str(exc_info.value)

    def test_command_with_arguments(self):
        """run_command handles commands with multiple arguments."""
        result = run_command(["echo", "-n", "test output"])
        assert result.returncode == 0
        assert b"test output" in result.stdout

    def test_command_captures_output(self):
        """run_command captures stdout."""
        result = run_command(["echo", "captured"])
        assert b"captured" in result.stdout

    def test_command_with_cwd(self):
        """run_command respects cwd parameter."""
        result = run_command(["pwd"], cwd="/tmp", text=True)
        assert (
            "/tmp" in result.stdout or "/private/tmp" in result.stdout
        )  # macOS uses /private/tmp

    def test_command_with_env(self):
        """run_command respects env parameter."""
        custom_env = {"MY_TEST_VAR": "test_value_12345"}
        result = run_command(
            ["sh", "-c", "echo $MY_TEST_VAR"],
            env=custom_env,
            text=True,
        )
        assert "test_value_12345" in result.stdout

    def test_command_with_text_true(self):
        """run_command returns text when text=True."""
        result = run_command(["echo", "hello"], text=True)
        assert isinstance(result.stdout, str)
        assert "hello" in result.stdout

    def test_command_with_text_false(self):
        """run_command returns bytes when text=False (default)."""
        result = run_command(["echo", "hello"], text=False)
        assert isinstance(result.stdout, bytes)
        assert b"hello" in result.stdout

    def test_command_failure_with_text_mode(self):
        """run_command captures stderr as text when text=True."""
        with pytest.raises(CommandFailedError) as exc_info:
            run_command(
                ["sh", "-c", "echo text_error >&2; exit 1"],
                text=True,
            )
        assert "text_error" in exc_info.value.stderr

    def test_command_with_all_options(self):
        """run_command works with all options combined."""
        custom_env = {"GREETING": "Hello"}
        result = run_command(
            ["sh", "-c", "echo $GREETING from $(pwd)"],
            cwd="/tmp",
            env=custom_env,
            text=True,
            timeout=5,
        )
        assert "Hello" in result.stdout
        assert "tmp" in result.stdout


class TestTryCommands:
    """Tests for try_commands function."""

    def test_first_command_succeeds(self):
        """try_commands returns first successful method name."""
        commands = [
            (["true"], "first method"),
            (["true"], "second method"),
        ]
        result = try_commands(commands)
        assert result == "first method"

    def test_fallback_to_second_command(self):
        """try_commands falls back when first command fails."""
        commands = [
            (["false"], "failing method"),
            (["true"], "working method"),
        ]
        result = try_commands(commands)
        assert result == "working method"

    def test_fallback_to_third_command(self):
        """try_commands can fall through multiple failures."""
        commands = [
            (["false"], "first failing"),
            (["nonexistent_xyz"], "second failing"),
            (["true"], "finally works"),
        ]
        result = try_commands(commands)
        assert result == "finally works"

    def test_all_commands_fail(self):
        """try_commands raises CommandError when all fail."""
        commands = [
            (["false"], "method A"),
            (["nonexistent_xyz"], "method B"),
        ]

        with pytest.raises(CommandError) as exc_info:
            try_commands(commands)

        error_msg = str(exc_info.value)
        assert "all methods failed" in error_msg
        assert "method A" in error_msg
        assert "method B" in error_msg
        assert "exited with code 1" in error_msg
        assert "not found" in error_msg

    def test_empty_commands_list(self):
        """try_commands raises when given empty list."""
        with pytest.raises(CommandError) as exc_info:
            try_commands([])

        assert "all methods failed" in str(exc_info.value)

    def test_custom_timeout(self):
        """try_commands respects timeout parameter."""
        commands = [
            (["sleep", "10"], "slow command"),
        ]

        with pytest.raises(CommandError) as exc_info:
            try_commands(commands, timeout=1)

        assert "timed out" in str(exc_info.value)

    def test_error_messages_are_combined(self):
        """try_commands combines all error messages."""
        commands = [
            (["sh", "-c", "echo err1 >&2; exit 1"], "cmd1"),
            (["sh", "-c", "echo err2 >&2; exit 2"], "cmd2"),
        ]

        with pytest.raises(CommandError) as exc_info:
            try_commands(commands)

        error_msg = exc_info.value.message
        assert "cmd1:" in error_msg
        assert "cmd2:" in error_msg


class TestCommandErrorInheritance:
    """Test that exceptions can be caught at different levels."""

    def test_catch_specific_error(self):
        """Can catch specific error types."""
        caught = None
        try:
            run_command(["nonexistent_xyz"])
        except CommandNotFoundError as e:
            caught = e

        assert caught is not None
        assert isinstance(caught, CommandNotFoundError)

    def test_catch_base_error(self):
        """Can catch all command errors with base class."""
        errors_caught = []

        # CommandNotFoundError
        try:
            run_command(["nonexistent_xyz"])
        except CommandError as e:
            errors_caught.append(type(e).__name__)

        # CommandFailedError
        try:
            run_command(["false"])
        except CommandError as e:
            errors_caught.append(type(e).__name__)

        assert "CommandNotFoundError" in errors_caught
        assert "CommandFailedError" in errors_caught

    def test_exception_is_standard_exception(self):
        """CommandError inherits from Exception."""
        assert issubclass(CommandError, Exception)

        # Can be caught with bare except (not recommended but should work)
        # Should not raise
        with suppress(Exception):
            run_command(["nonexistent_xyz"])
