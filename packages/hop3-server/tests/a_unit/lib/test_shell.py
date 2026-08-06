# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for shell command execution utilities."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hop3.lib.console import capture_logs
from hop3.lib.sh import (
    _log_error,
    _log_output,
    _needs_shell,
    _parse_command,
    _resolve_cwd,
    shell,
)


def _logged_text(captured) -> str:
    """Join all captured log messages into a single searchable string."""
    return "\n".join(entry["msg"] for entry in captured.get_logs())


class TestNeedsShell:
    """Tests for the _needs_shell predicate."""

    @pytest.mark.parametrize(
        "command",
        [
            "foo && bar",
            "foo || bar",
            "foo; bar",
            "foo | bar",
            "foo > out.txt",
            "foo >> out.txt",
            "foo < in.txt",
            "echo $(date)",
        ],
    )
    def test_shell_operators_require_shell(self, command):
        """Commands containing shell operators need sh -c."""
        assert _needs_shell(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "ls -la",
            "echo hello world",
            "git status",
            "python3 -m pytest",
        ],
    )
    def test_plain_commands_do_not_need_shell(self, command):
        """Plain commands with no operators do not need sh -c."""
        assert _needs_shell(command) is False

    def test_leading_env_assignment_requires_shell(self):
        """A leading VAR=value assignment requires sh -c."""
        assert _needs_shell("CI=true bin/script.sh") is True

    def test_equals_in_later_token_does_not_require_shell(self):
        """An '=' in a non-first token (e.g. a flag) does not trigger sh -c."""
        assert _needs_shell("mycmd --opt=value") is False

    def test_empty_command_does_not_need_shell(self):
        """An empty command string does not need sh -c."""
        assert _needs_shell("") is False

    def test_whitespace_only_command_does_not_need_shell(self):
        """A whitespace-only command does not need sh -c (no first token)."""
        assert _needs_shell("   ") is False


class TestParseCommand:
    """Tests for the _parse_command function."""

    def test_plain_string_is_split(self):
        """A plain string is shlex-split into an argument list."""
        display, command_list = _parse_command("echo hello world")

        assert display == "echo hello world"
        assert command_list == ["echo", "hello", "world"]

    def test_string_is_stripped_for_display(self):
        """Surrounding whitespace is stripped from the display string."""
        display, command_list = _parse_command("  ls -la  ")

        assert display == "ls -la"
        assert command_list == ["ls", "-la"]

    def test_quoted_string_respects_shlex_rules(self):
        """shlex.split keeps quoted segments as single arguments."""
        _display, command_list = _parse_command('echo "hello world"')

        assert command_list == ["echo", "hello world"]

    def test_string_with_operator_is_wrapped_in_sh_c(self):
        """A string with a shell operator is wrapped in sh -c verbatim."""
        display, command_list = _parse_command("echo a && echo b")

        assert display == "echo a && echo b"
        assert command_list == ["sh", "-c", "echo a && echo b"]

    def test_string_with_env_assignment_is_wrapped_in_sh_c(self):
        """A leading env assignment is wrapped in sh -c."""
        _display, command_list = _parse_command("FOO=bar mycmd")

        assert command_list == ["sh", "-c", "FOO=bar mycmd"]

    def test_list_is_passed_through_and_joined_for_display(self):
        """A list is returned unchanged, with a shlex-joined display string."""
        display, command_list = _parse_command(["echo", "hello world"])

        assert command_list == ["echo", "hello world"]
        # shlex.join quotes the argument containing a space
        assert display == "echo 'hello world'"

    def test_non_string_non_list_raises_type_error(self):
        """Passing an unsupported type raises TypeError."""
        with pytest.raises(TypeError, match="string or a list"):
            _parse_command(42)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


class TestResolveCwd:
    """Tests for the _resolve_cwd function."""

    def test_empty_string_returns_current_directory(self):
        """An empty cwd resolves to the current working directory."""
        assert _resolve_cwd("") == Path.cwd()

    def test_path_is_resolved_to_absolute(self, tmp_path):
        """A relative-or-absolute path is resolved to an absolute Path."""
        result = _resolve_cwd(tmp_path)

        assert result == tmp_path.resolve()
        assert result.is_absolute()

    def test_string_path_is_accepted(self, tmp_path):
        """A string path is converted and resolved to a Path."""
        result = _resolve_cwd(str(tmp_path))

        assert isinstance(result, Path)
        assert result == tmp_path.resolve()


class TestLogOutput:
    """Tests for the _log_output helper (observed via captured logs)."""

    def test_multiline_output_logs_each_line(self):
        """Each line of multi-line output is logged as a separate entry."""
        with capture_logs(verbosity=3) as captured:
            _log_output("line one\nline two\nline three", level=1)

        messages = [entry["msg"] for entry in captured.get_logs()]
        assert any("line one" in m for m in messages)
        assert any("line two" in m for m in messages)
        assert any("line three" in m for m in messages)
        assert len(messages) == 3

    def test_trailing_newline_is_stripped(self):
        """A trailing newline does not produce an extra blank log entry."""
        with capture_logs(verbosity=3) as captured:
            _log_output("only line\n", level=1)

        messages = [entry["msg"] for entry in captured.get_logs()]
        assert len(messages) == 1
        assert "only line" in messages[0]

    def test_single_line_output_is_logged(self):
        """A single line with no newline is logged."""
        with capture_logs(verbosity=3) as captured:
            _log_output("single", level=1)

        assert "single" in _logged_text(captured)

    def test_uses_requested_color(self):
        """The fg color argument is propagated to the log entry."""
        with capture_logs(verbosity=3) as captured:
            _log_output("colored", level=1, fg="yellow")

        assert captured.get_logs()[0]["fg"] == "yellow"


class TestLogError:
    """Tests for the _log_error helper (observed via captured logs)."""

    def test_logs_exit_code_and_command(self):
        """The failure header includes the exit code and the command."""
        err = subprocess.CalledProcessError(returncode=3, cmd=["false"])

        with capture_logs(verbosity=3) as captured:
            _log_error("my-command", err)

        text = _logged_text(captured)
        assert "exit code 3" in text
        assert "my-command" in text

    def test_logs_stdout_section_when_present(self):
        """Captured stdout is reported under a Stdout: section."""
        err = subprocess.CalledProcessError(
            returncode=1, cmd=["x"], output="out-content"
        )

        with capture_logs(verbosity=3) as captured:
            _log_error("cmd", err)

        text = _logged_text(captured)
        assert "Stdout:" in text
        assert "out-content" in text

    def test_logs_stderr_section_when_present(self):
        """Captured stderr is reported under a Stderr: section."""
        err = subprocess.CalledProcessError(returncode=1, cmd=["x"])
        err.stderr = "err-content"

        with capture_logs(verbosity=3) as captured:
            _log_error("cmd", err)

        text = _logged_text(captured)
        assert "Stderr:" in text
        assert "err-content" in text

    def test_omits_sections_when_no_output(self):
        """No Stdout/Stderr sections are emitted when both are empty."""
        err = subprocess.CalledProcessError(returncode=1, cmd=["x"])

        with capture_logs(verbosity=3) as captured:
            _log_error("cmd", err)

        text = _logged_text(captured)
        assert "Stdout:" not in text
        assert "Stderr:" not in text


class TestShell:
    """End-to-end tests for shell() using real subprocesses."""

    def test_successful_string_command_returns_completed_process(self):
        """A successful string command returns a CompletedProcess."""
        result = shell("echo hello")

        assert isinstance(result, subprocess.CompletedProcess)
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_successful_list_command_returns_completed_process(self):
        """A successful list command returns a CompletedProcess."""
        result = shell(["echo", "world"])

        assert result.returncode == 0
        assert "world" in result.stdout

    def test_runs_in_given_cwd(self, tmp_path):
        """The command runs in the resolved working directory."""
        marker = tmp_path / "marker.txt"
        marker.write_text("present")

        result = shell("ls", cwd=tmp_path)

        assert "marker.txt" in result.stdout

    def test_shell_operator_command_executes_via_sh(self):
        """A command with a shell operator runs through sh -c."""
        result = shell("echo a && echo b")

        assert "a" in result.stdout
        assert "b" in result.stdout

    def test_failing_command_raises_called_process_error(self):
        """A failing command raises CalledProcessError by default."""
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            shell("false")

        assert exc_info.value.returncode == 1

    def test_failing_command_error_preserves_output(self):
        """The re-raised error carries the captured stdout and stderr."""
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            shell("sh -c 'echo out; echo err >&2; exit 7'")

        err = exc_info.value
        assert err.returncode == 7
        assert "out" in err.stdout
        assert "err" in err.stderr

    def test_check_false_suppresses_error(self):
        """Passing check=False returns the failing CompletedProcess."""
        result = shell("false", check=False)

        assert result.returncode == 1

    def test_logs_command_invocation(self):
        """The command invocation is logged before execution."""
        with capture_logs(verbosity=3) as captured:
            shell("echo logged")

        text = _logged_text(captured)
        assert "Calling:" in text
        assert "echo logged" in text
