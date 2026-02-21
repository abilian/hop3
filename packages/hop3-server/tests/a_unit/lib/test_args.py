# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the declarative CLI argument parser."""
from __future__ import annotations

from hop3.lib.args import parse_cli_args


class TestParseCliArgs:
    """Tests for parse_cli_args function."""

    def test_positional_argument(self):
        """Test parsing a positional argument."""
        spec = {"app_name": {"positional": True}}
        result = parse_cli_args(("myapp",), spec)
        assert result == {"app_name": "myapp"}

    def test_positional_with_default(self):
        """Test positional argument with default when not provided."""
        spec = {"app_name": {"positional": True, "default": "default_app"}}
        result = parse_cli_args((), spec)
        assert result == {"app_name": "default_app"}

    def test_short_option(self):
        """Test parsing short option with value."""
        spec = {"lines": {"short": "-n", "type": int}}
        result = parse_cli_args(("-n", "50"), spec)
        assert result == {"lines": 50}

    def test_short_option_with_default(self):
        """Test short option uses default when not provided."""
        spec = {"lines": {"short": "-n", "type": int, "default": 100}}
        result = parse_cli_args((), spec)
        assert result == {"lines": 100}

    def test_long_option_with_value(self):
        """Test parsing --key value format."""
        spec = {"grep": {"type": str}}
        result = parse_cli_args(("--grep", "error"), spec)
        assert result == {"grep": "error"}

    def test_long_option_with_equals(self):
        """Test parsing --key=value format."""
        spec = {"grep": {"type": str}}
        result = parse_cli_args(("--grep=error",), spec)
        assert result == {"grep": "error"}

    def test_flag_option(self):
        """Test parsing boolean flag."""
        spec = {"verbose": {"flag": True}}
        result = parse_cli_args(("--verbose",), spec)
        assert result == {"verbose": True}

    def test_flag_option_not_provided(self):
        """Test flag defaults to not present (no default set)."""
        spec = {"verbose": {"flag": True}}
        result = parse_cli_args((), spec)
        assert result == {}

    def test_flag_with_default_false(self):
        """Test flag with explicit default False."""
        spec = {"verbose": {"flag": True, "default": False}}
        result = parse_cli_args((), spec)
        assert result == {"verbose": False}

    def test_hyphenated_flag(self):
        """Test flag with hyphen converts to underscore."""
        spec = {"since_deploy": {"flag": True}}
        result = parse_cli_args(("--since-deploy",), spec)
        assert result == {"since_deploy": True}

    def test_combined_positional_and_options(self):
        """Test parsing positional with multiple options."""
        spec = {
            "app_name": {"positional": True},
            "lines": {"short": "-n", "type": int, "default": 100},
            "grep": {"type": str, "default": ""},
            "since_deploy": {"flag": True, "default": False},
        }
        result = parse_cli_args(("myapp", "-n", "50", "--since-deploy"), spec)
        assert result == {
            "app_name": "myapp",
            "lines": 50,
            "grep": "",
            "since_deploy": True,
        }

    def test_options_before_positional(self):
        """Test that options can come before positional argument."""
        spec = {
            "app_name": {"positional": True},
            "verbose": {"flag": True},
        }
        result = parse_cli_args(("--verbose", "myapp"), spec)
        assert result == {"app_name": "myapp", "verbose": True}

    def test_type_conversion_int(self):
        """Test integer type conversion."""
        spec = {"count": {"type": int}}
        result = parse_cli_args(("--count", "42"), spec)
        assert result == {"count": 42}
        assert isinstance(result["count"], int)

    def test_type_conversion_with_equals(self):
        """Test type conversion with --key=value format."""
        spec = {"lines": {"type": int}}
        result = parse_cli_args(("--lines=25",), spec)
        assert result == {"lines": 25}
        assert isinstance(result["lines"], int)

    def test_multiple_short_options(self):
        """Test multiple short options."""
        spec = {
            "lines": {"short": "-n", "type": int},
            "timeout": {"short": "-t", "type": int},
        }
        result = parse_cli_args(("-n", "100", "-t", "30"), spec)
        assert result == {"lines": 100, "timeout": 30}

    def test_empty_args(self):
        """Test with empty arguments."""
        spec = {"app_name": {"positional": True}}
        result = parse_cli_args((), spec)
        assert result == {}

    def test_empty_spec(self):
        """Test with empty specification."""
        result = parse_cli_args(("arg1", "arg2"), {})
        assert result == {}

    def test_unknown_options_ignored(self):
        """Test that unknown options are ignored."""
        spec = {"app_name": {"positional": True}}
        result = parse_cli_args(("myapp", "--unknown", "value"), spec)
        assert result == {"app_name": "myapp"}

    def test_list_input(self):
        """Test that list input works same as tuple."""
        spec = {"app_name": {"positional": True}}
        result = parse_cli_args(["myapp"], spec)
        assert result == {"app_name": "myapp"}

    def test_defaults_applied_last(self):
        """Test that defaults are applied for missing arguments."""
        spec = {
            "app_name": {"positional": True},
            "lines": {"short": "-n", "type": int, "default": 100},
            "verbose": {"flag": True, "default": False},
        }
        result = parse_cli_args(("myapp",), spec)
        assert result == {"app_name": "myapp", "lines": 100, "verbose": False}

    def test_real_world_logs_command(self):
        """Test realistic LogsCmd argument parsing."""
        spec = {
            "app_name": {"positional": True},
            "lines": {"short": "-n", "type": int, "default": 100},
            "grep": {"type": str, "default": ""},
            "since_deploy": {"flag": True, "default": False},
        }

        # Basic usage
        assert parse_cli_args(("myapp",), spec) == {
            "app_name": "myapp",
            "lines": 100,
            "grep": "",
            "since_deploy": False,
        }

        # With line count
        assert parse_cli_args(("myapp", "-n", "50"), spec) == {
            "app_name": "myapp",
            "lines": 50,
            "grep": "",
            "since_deploy": False,
        }

        # With grep
        assert parse_cli_args(("myapp", "--grep", "error"), spec) == {
            "app_name": "myapp",
            "lines": 100,
            "grep": "error",
            "since_deploy": False,
        }

        # With flag
        assert parse_cli_args(("myapp", "--since-deploy"), spec) == {
            "app_name": "myapp",
            "lines": 100,
            "grep": "",
            "since_deploy": True,
        }

        # All options combined
        assert parse_cli_args(
            ("myapp", "-n", "25", "--grep=warning", "--since-deploy"), spec
        ) == {
            "app_name": "myapp",
            "lines": 25,
            "grep": "warning",
            "since_deploy": True,
        }

    def test_real_world_env_command(self):
        """Test realistic EnvCmd argument parsing."""
        spec = {
            "app_name": {"positional": True},
            "show_secrets": {"flag": True, "default": False},
        }

        assert parse_cli_args(("myapp",), spec) == {
            "app_name": "myapp",
            "show_secrets": False,
        }

        assert parse_cli_args(("myapp", "--show-secrets"), spec) == {
            "app_name": "myapp",
            "show_secrets": True,
        }
