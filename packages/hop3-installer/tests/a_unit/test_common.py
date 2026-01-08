# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for hop3_installer.common module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from hop3_installer.common import (
    MIN_PYTHON,
    Colors,
    CommandError,
    CommandResult,
    Spinner,
    check_python_version,
    cmd_exists,
    detect_distro,
    env_bool,
    env_list,
    env_path,
    env_str,
    find_project_root,
    get_current_shell,
    print_detail,
    print_error,
    print_header,
    print_info,
    print_step,
    print_success,
    print_warning,
    run_cmd,
)

# =============================================================================
# Colors Tests
# =============================================================================


class TestColors:
    """Tests for Colors class."""

    def test_colors_have_ansi_codes(self):
        """Colors should have ANSI escape codes by default."""
        # Note: Colors may be disabled if not running in TTY
        # We test the class attributes directly
        assert hasattr(Colors, "RESET")
        assert hasattr(Colors, "RED")
        assert hasattr(Colors, "GREEN")
        assert hasattr(Colors, "BOLD")

    def test_colors_disable_sets_empty_strings(self):
        """disable() should set all color attributes to empty strings."""
        # Save original values
        original_reset = Colors.RESET
        original_red = Colors.RED

        # Disable colors
        Colors.disable()

        # Verify all are empty
        assert Colors.RESET == ""
        assert Colors.RED == ""
        assert Colors.GREEN == ""
        assert Colors.BOLD == ""

        # Restore for other tests (set back to ANSI codes)
        Colors.RESET = "\033[0m"
        Colors.BOLD = "\033[1m"
        Colors.DIM = "\033[2m"
        Colors.RED = "\033[0;31m"
        Colors.GREEN = "\033[0;32m"
        Colors.YELLOW = "\033[0;33m"
        Colors.BLUE = "\033[0;34m"
        Colors.CYAN = "\033[0;36m"


# =============================================================================
# CommandResult Tests
# =============================================================================


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_success_when_returncode_zero(self):
        """success property should be True when returncode is 0."""
        result = CommandResult(returncode=0, stdout="output", stderr="")
        assert result.success is True

    def test_failure_when_returncode_nonzero(self):
        """success property should be False when returncode is non-zero."""
        result = CommandResult(returncode=1, stdout="", stderr="error")
        assert result.success is False

    def test_default_values(self):
        """CommandResult should have sensible defaults."""
        result = CommandResult(returncode=0)
        assert result.stdout == ""
        assert result.stderr == ""


# =============================================================================
# CommandError Tests
# =============================================================================


class TestCommandError:
    """Tests for CommandError exception."""

    def test_error_contains_command(self):
        """CommandError string should contain the failed command."""
        error = CommandError(
            cmd=["ls", "-la", "/nonexistent"],
            returncode=2,
            stderr="No such file",
        )
        assert "ls" in str(error)
        assert "-la" in str(error)

    def test_error_attributes(self):
        """CommandError should store all relevant attributes."""
        error = CommandError(
            cmd=["test", "cmd"],
            returncode=127,
            stderr="command not found",
            stdout="",
        )
        assert error.cmd == ["test", "cmd"]
        assert error.returncode == 127
        assert error.stderr == "command not found"


# =============================================================================
# run_cmd Tests
# =============================================================================


class TestRunCmd:
    """Tests for run_cmd function."""

    def test_run_successful_command(self):
        """run_cmd should execute command and return result."""
        result = run_cmd(["echo", "hello"])
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_run_command_with_check_false(self):
        """run_cmd with check=False should not raise on failure."""
        # Using a command that will fail
        result = run_cmd(["false"], check=False)
        assert result.returncode != 0

    def test_run_command_with_check_true_raises(self):
        """run_cmd with check=True should raise CommandError on failure."""
        with pytest.raises(CommandError) as exc_info:
            run_cmd(["false"], check=True)
        assert exc_info.value.returncode != 0

    def test_run_command_with_env(self):
        """run_cmd should pass environment variables."""
        result = run_cmd(
            ["sh", "-c", "echo $TEST_VAR"],
            env={"TEST_VAR": "test_value"},
        )
        assert "test_value" in result.stdout

    def test_run_command_with_timeout(self):
        """run_cmd should handle timeout."""
        result = run_cmd(["sleep", "10"], timeout=0.1, check=False)
        assert result.returncode == -1
        assert "timed out" in result.stderr.lower()

    def test_run_command_capture_false(self):
        """run_cmd with capture=False should not capture output."""
        result = run_cmd(["echo", "hello"], capture=False)
        assert result.returncode == 0
        # stdout/stderr are not captured
        assert result.stdout is None or result.stdout == ""


# =============================================================================
# cmd_exists Tests
# =============================================================================


class TestCmdExists:
    """Tests for cmd_exists function."""

    def test_existing_command(self):
        """cmd_exists should return True for existing commands."""
        assert cmd_exists("ls") is True
        assert cmd_exists("echo") is True

    def test_nonexistent_command(self):
        """cmd_exists should return False for non-existing commands."""
        assert cmd_exists("nonexistent_command_12345") is False

    def test_python_exists(self):
        """cmd_exists should find python3."""
        # python3 should exist on any system running these tests
        assert cmd_exists("python3") is True


# =============================================================================
# get_current_shell Tests
# =============================================================================


class TestGetCurrentShell:
    """Tests for get_current_shell function."""

    def test_detects_bash(self, clean_env):
        """get_current_shell should detect bash."""
        clean_env["SHELL"] = "/bin/bash"
        assert get_current_shell() == "bash"

    def test_detects_zsh(self, clean_env):
        """get_current_shell should detect zsh."""
        clean_env["SHELL"] = "/bin/zsh"
        assert get_current_shell() == "zsh"

    def test_detects_fish(self, clean_env):
        """get_current_shell should detect fish."""
        clean_env["SHELL"] = "/usr/bin/fish"
        assert get_current_shell() == "fish"

    def test_returns_none_for_unknown(self, clean_env):
        """get_current_shell should return None for unknown shells."""
        clean_env["SHELL"] = "/bin/unknown"
        assert get_current_shell() is None

    def test_returns_none_when_not_set(self, clean_env):
        """get_current_shell should return None when SHELL not set."""
        clean_env.pop("SHELL", None)
        assert get_current_shell() is None


# =============================================================================
# find_project_root Tests
# =============================================================================


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_finds_root_with_pyproject_and_packages(self, mock_project_root: Path):
        """find_project_root should find root with pyproject.toml and packages/."""
        # Start from a subdirectory
        start = mock_project_root / "packages" / "hop3-server"
        result = find_project_root(start)
        assert result == mock_project_root

    def test_finds_root_with_git_and_packages(self, tmp_path: Path):
        """find_project_root should find root with .git and packages/."""
        root = tmp_path / "project"
        root.mkdir()
        (root / ".git").mkdir()
        (root / "packages").mkdir()

        start = root / "packages"
        result = find_project_root(start)
        assert result == root

    def test_returns_cwd_when_not_found(self, tmp_path: Path):
        """find_project_root should return cwd when root not found."""
        # tmp_path has no pyproject.toml or packages/
        result = find_project_root(tmp_path)
        # Should return cwd since no project root found
        assert result == Path.cwd()

    def test_uses_cwd_when_no_start_path(self):
        """find_project_root should use cwd when start_path is None."""
        result = find_project_root(None)
        # Should return something (either project root or cwd)
        assert isinstance(result, Path)


# =============================================================================
# Print Functions Tests
# =============================================================================


class TestPrintFunctions:
    """Tests for print_* functions."""

    def test_print_header(self, capsys):
        """print_header should print styled header."""
        print_header("Test Title")
        captured = capsys.readouterr()
        assert "Test Title" in captured.out
        assert "=" in captured.out  # Underline

    def test_print_step(self, capsys):
        """print_step should print step indicator."""
        print_step(1, 5, "Installing")
        captured = capsys.readouterr()
        assert "[1/5]" in captured.out
        assert "Installing" in captured.out

    def test_print_success(self, capsys):
        """print_success should print success message."""
        print_success("Done!")
        captured = capsys.readouterr()
        assert "Done!" in captured.out

    def test_print_info(self, capsys):
        """print_info should print info message."""
        print_info("Information")
        captured = capsys.readouterr()
        assert "Information" in captured.out

    def test_print_warning(self, capsys):
        """print_warning should print warning message."""
        print_warning("Careful!")
        captured = capsys.readouterr()
        assert "Careful!" in captured.out

    def test_print_error(self, capsys):
        """print_error should print to stderr."""
        print_error("Failed!")
        captured = capsys.readouterr()
        assert "Failed!" in captured.err  # Note: stderr

    def test_print_detail(self, capsys):
        """print_detail should print detail message."""
        print_detail("Sub-item info")
        captured = capsys.readouterr()
        assert "Sub-item info" in captured.out


# =============================================================================
# detect_distro Tests
# =============================================================================


class TestDetectDistro:
    """Tests for detect_distro function."""

    def test_detects_debian_content(self, sample_os_release_debian: Path):
        """Sample Debian os-release should contain debian/ubuntu."""
        content = sample_os_release_debian.read_text()
        assert "ubuntu" in content.lower() or "debian" in content.lower()

    def test_detects_fedora_content(self, sample_os_release_fedora: Path):
        """Sample Fedora os-release should contain fedora."""
        content = sample_os_release_fedora.read_text()
        assert "fedora" in content.lower()

    def test_returns_unknown_for_missing_file(self):
        """detect_distro should return 'unknown' when /etc/os-release missing."""
        with patch("hop3_installer.common.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            result = detect_distro()
            assert result == "unknown"


# =============================================================================
# Spinner Tests
# =============================================================================


class TestSpinner:
    """Tests for Spinner context manager."""

    def test_spinner_context_manager_non_tty(self, capsys):
        """Spinner should print message when not a TTY."""
        # When not a TTY, spinner just prints the message
        with patch("sys.stdout.isatty", return_value=False):
            with Spinner("Loading..."):
                pass
        captured = capsys.readouterr()
        assert "Loading..." in captured.out

    def test_spinner_stores_message(self):
        """Spinner should store the message."""
        spinner = Spinner("Test message")
        assert spinner.message == "Test message"

    def test_spinner_has_chars(self):
        """Spinner should have animation characters."""
        assert len(Spinner.CHARS) > 0
        assert isinstance(Spinner.CHARS, str)

    def test_spinner_enter_exit(self):
        """Spinner should work as context manager."""
        spinner = Spinner("Test")
        with patch("sys.stdout.isatty", return_value=False):
            result = spinner.__enter__()
            assert result is spinner
            spinner.__exit__(None, None, None)


# =============================================================================
# check_python_version Tests
# =============================================================================


class TestCheckPythonVersion:
    """Tests for check_python_version function."""

    def test_min_python_is_tuple(self):
        """MIN_PYTHON should be a tuple of two ints."""
        assert isinstance(MIN_PYTHON, tuple)
        assert len(MIN_PYTHON) == 2
        assert all(isinstance(v, int) for v in MIN_PYTHON)

    def test_current_python_meets_requirement(self):
        """Current Python should meet MIN_PYTHON requirement."""
        # If we're running these tests, Python version should be sufficient
        assert sys.version_info >= MIN_PYTHON

    def test_check_python_version_exits_on_old_python(self):
        """check_python_version should exit for old Python."""

        # Create a class that behaves like sys.version_info
        class MockVersionInfo:
            major = 3
            minor = 8

            def __lt__(self, other):
                return (self.major, self.minor) < other

            def __ge__(self, other):
                return (self.major, self.minor) >= other

        with patch.object(sys, "version_info", MockVersionInfo()):
            with pytest.raises(SystemExit) as exc_info:
                check_python_version()
            assert exc_info.value.code == 1

    def test_check_python_version_passes_for_current(self):
        """check_python_version should not exit for current Python."""
        # Should not raise - we're running on a valid Python
        check_python_version()  # No exception expected


# =============================================================================
# Environment Variable Helper Tests
# =============================================================================


class TestEnvStr:
    """Tests for env_str function."""

    def test_returns_value_when_set(self, clean_env):
        """env_str should return value when env var is set."""
        clean_env["TEST_VAR"] = "test_value"
        assert env_str("TEST_VAR") == "test_value"

    def test_returns_none_when_not_set(self, clean_env):
        """env_str should return None when env var is not set."""
        clean_env.pop("TEST_VAR", None)
        assert env_str("TEST_VAR") is None

    def test_returns_default_when_not_set(self, clean_env):
        """env_str should return default when env var is not set."""
        clean_env.pop("TEST_VAR", None)
        assert env_str("TEST_VAR", "default") == "default"

    def test_returns_value_over_default(self, clean_env):
        """env_str should return value even when default is provided."""
        clean_env["TEST_VAR"] = "actual"
        assert env_str("TEST_VAR", "default") == "actual"

    def test_returns_empty_string_when_set_empty(self, clean_env):
        """env_str should return empty string when set to empty."""
        clean_env["TEST_VAR"] = ""
        assert env_str("TEST_VAR") == ""


class TestEnvBool:
    """Tests for env_bool function."""

    def test_returns_true_for_1(self, clean_env):
        """env_bool should return True for '1'."""
        clean_env["TEST_VAR"] = "1"
        assert env_bool("TEST_VAR") is True

    def test_returns_true_for_true_lowercase(self, clean_env):
        """env_bool should return True for 'true'."""
        clean_env["TEST_VAR"] = "true"
        assert env_bool("TEST_VAR") is True

    def test_returns_true_for_true_uppercase(self, clean_env):
        """env_bool should return True for 'TRUE'."""
        clean_env["TEST_VAR"] = "TRUE"
        assert env_bool("TEST_VAR") is True

    def test_returns_true_for_true_mixed_case(self, clean_env):
        """env_bool should return True for 'True'."""
        clean_env["TEST_VAR"] = "True"
        assert env_bool("TEST_VAR") is True

    def test_returns_false_for_0(self, clean_env):
        """env_bool should return False for '0'."""
        clean_env["TEST_VAR"] = "0"
        assert env_bool("TEST_VAR") is False

    def test_returns_false_for_false(self, clean_env):
        """env_bool should return False for 'false'."""
        clean_env["TEST_VAR"] = "false"
        assert env_bool("TEST_VAR") is False

    def test_returns_false_for_other_values(self, clean_env):
        """env_bool should return False for other values."""
        clean_env["TEST_VAR"] = "yes"
        assert env_bool("TEST_VAR") is False

    def test_returns_false_when_not_set(self, clean_env):
        """env_bool should return False when env var is not set."""
        clean_env.pop("TEST_VAR", None)
        assert env_bool("TEST_VAR") is False


class TestEnvPath:
    """Tests for env_path function."""

    def test_returns_path_when_set(self, clean_env):
        """env_path should return Path when env var is set."""
        clean_env["TEST_VAR"] = "/some/path"
        result = env_path("TEST_VAR", Path("/default"))
        assert result == Path("/some/path")

    def test_returns_default_when_not_set(self, clean_env):
        """env_path should return default when env var is not set."""
        clean_env.pop("TEST_VAR", None)
        default = Path("/default/path")
        result = env_path("TEST_VAR", default)
        assert result == default

    def test_returns_default_when_empty(self, clean_env):
        """env_path should return default when env var is empty."""
        clean_env["TEST_VAR"] = ""
        default = Path("/default/path")
        result = env_path("TEST_VAR", default)
        assert result == default

    def test_handles_relative_paths(self, clean_env):
        """env_path should handle relative paths."""
        clean_env["TEST_VAR"] = "relative/path"
        result = env_path("TEST_VAR", Path("/default"))
        assert result == Path("relative/path")


class TestEnvList:
    """Tests for env_list function."""

    def test_returns_list_from_comma_separated(self, clean_env):
        """env_list should split comma-separated values."""
        clean_env["TEST_VAR"] = "a,b,c"
        result = env_list("TEST_VAR")
        assert result == ["a", "b", "c"]

    def test_strips_whitespace(self, clean_env):
        """env_list should strip whitespace from items."""
        clean_env["TEST_VAR"] = " a , b , c "
        result = env_list("TEST_VAR")
        assert result == ["a", "b", "c"]

    def test_filters_empty_items(self, clean_env):
        """env_list should filter empty items."""
        clean_env["TEST_VAR"] = "a,,b,  ,c"
        result = env_list("TEST_VAR")
        assert result == ["a", "b", "c"]

    def test_returns_empty_list_when_not_set(self, clean_env):
        """env_list should return empty list when env var is not set."""
        clean_env.pop("TEST_VAR", None)
        result = env_list("TEST_VAR")
        assert result == []

    def test_returns_empty_list_when_empty(self, clean_env):
        """env_list should return empty list when env var is empty."""
        clean_env["TEST_VAR"] = ""
        result = env_list("TEST_VAR")
        assert result == []

    def test_custom_separator(self, clean_env):
        """env_list should use custom separator."""
        clean_env["TEST_VAR"] = "a:b:c"
        result = env_list("TEST_VAR", separator=":")
        assert result == ["a", "b", "c"]

    def test_single_item(self, clean_env):
        """env_list should handle single item."""
        clean_env["TEST_VAR"] = "single"
        result = env_list("TEST_VAR")
        assert result == ["single"]
