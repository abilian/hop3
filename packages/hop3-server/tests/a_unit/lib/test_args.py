# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the declarative CLI argument parser."""

from __future__ import annotations

import pytest

from hop3.lib.args import parse_cli_args, pop_app_flag, reject_extra_args


class TestPopAppFlag:
    """The app is a flag, never a positional (ADR 036 D5)."""

    def test_extracts_app_and_keeps_settings(self):
        assert pop_app_flag(["--app", "myapp", "K=V"]) == ("myapp", ["K=V"])

    def test_equals_form(self):
        assert pop_app_flag(["--app=myapp", "K=V"]) == ("myapp", ["K=V"])

    def test_short_form(self):
        assert pop_app_flag(["-a", "myapp", "a", "b"]) == ("myapp", ["a", "b"])

    def test_flag_anywhere(self):
        assert pop_app_flag(["K=V", "--app", "myapp"]) == ("myapp", ["K=V"])

    def test_no_flag_returns_none_and_all_args(self):
        # A KEY=VALUE is never an app — without --app the caller decides.
        assert pop_app_flag(["SENTRY_DSN=https://x@y/1"]) == (
            None,
            ["SENTRY_DSN=https://x@y/1"],
        )

    def test_empty(self):
        assert pop_app_flag([]) == (None, [])

    def test_dangling_flag_no_value(self):
        assert pop_app_flag(["--app"]) == (None, [])


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

    def test_empty_spec_rejects_extra_args(self):
        """An empty spec has no slot for tokens, so they must be rejected loudly
        rather than silently dropped (fail-loud rule)."""
        with pytest.raises(ValueError, match="Unrecognized argument"):
            parse_cli_args(("arg1", "arg2"), {})

    def test_unknown_options_rejected(self):
        """Unknown options must fail loud, not be silently ignored — a dropped
        `--key value` (or an extra positional) reads as success while doing
        nothing."""
        spec = {"app_name": {"positional": True}}
        with pytest.raises(ValueError, match="Unrecognized argument"):
            parse_cli_args(("myapp", "--unknown", "value"), spec)

    def test_extra_positional_without_slot_rejected(self):
        """The reported bug: `app env set KEY=VALUE` misroutes to a spec with no
        `set`/`remaining` slot; the trailing tokens must error, not vanish."""
        spec = {"app": {"type": str}, "show_secrets": {"flag": True}}
        with pytest.raises(ValueError, match=r"set.*APP_SECRET_KEY"):
            parse_cli_args(("--app", "myapp", "set", "APP_SECRET_KEY=zzz"), spec)

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

    # Tests for remaining args feature

    def test_remaining_args_basic(self):
        """Test collecting remaining args into a list."""
        spec = {
            "app_name": {"positional": True},
            "keys": {"remaining": True},
        }
        result = parse_cli_args(("myapp", "KEY1", "KEY2", "KEY3"), spec)
        assert result == {"app_name": "myapp", "keys": ["KEY1", "KEY2", "KEY3"]}

    def test_remaining_args_empty(self):
        """Test remaining args is empty list when no extra args."""
        spec = {
            "app_name": {"positional": True},
            "keys": {"remaining": True},
        }
        result = parse_cli_args(("myapp",), spec)
        assert result == {"app_name": "myapp", "keys": []}

    def test_remaining_args_with_options(self):
        """Test remaining args works with options interspersed."""
        spec = {
            "app_name": {"positional": True},
            "verbose": {"flag": True},
            "keys": {"remaining": True},
        }
        result = parse_cli_args(("myapp", "--verbose", "KEY1", "KEY2"), spec)
        assert result == {
            "app_name": "myapp",
            "verbose": True,
            "keys": ["KEY1", "KEY2"],
        }

    def test_remaining_args_options_after(self):
        """Test that options after positional still work."""
        spec = {
            "app_name": {"positional": True},
            "force": {"flag": True},
            "settings": {"remaining": True},
        }
        result = parse_cli_args(("myapp", "FOO=bar", "--force", "BAZ=qux"), spec)
        assert result == {
            "app_name": "myapp",
            "force": True,
            "settings": ["FOO=bar", "BAZ=qux"],
        }

    def test_remaining_only_no_positional(self):
        """Test remaining works without a positional arg."""
        spec = {"keys": {"remaining": True}}
        result = parse_cli_args(("KEY1", "KEY2"), spec)
        assert result == {"keys": ["KEY1", "KEY2"]}

    def test_remaining_with_default(self):
        """Test remaining with default value (not typical but should work)."""
        spec = {
            "app_name": {"positional": True},
            "keys": {"remaining": True, "default": ["default_key"]},
        }
        # When args provided, remaining is populated (not default)
        result = parse_cli_args(("myapp",), spec)
        # remaining is always initialized to [], default not applied since key exists
        assert result == {"app_name": "myapp", "keys": []}

    def test_real_world_config_unset(self):
        """Test realistic config:unset command."""
        spec = {
            "app_name": {"positional": True},
            "keys": {"remaining": True},
        }

        # Unset single key
        assert parse_cli_args(("myapp", "DATABASE_URL"), spec) == {
            "app_name": "myapp",
            "keys": ["DATABASE_URL"],
        }

        # Unset multiple keys
        assert parse_cli_args(("myapp", "KEY1", "KEY2", "KEY3"), spec) == {
            "app_name": "myapp",
            "keys": ["KEY1", "KEY2", "KEY3"],
        }

    def test_real_world_config_set(self):
        """Test realistic config:set command with KEY=VALUE pairs."""
        spec = {
            "app_name": {"positional": True},
            "settings": {"remaining": True},
        }

        # Set single var
        assert parse_cli_args(("myapp", "DATABASE_URL=postgres://..."), spec) == {
            "app_name": "myapp",
            "settings": ["DATABASE_URL=postgres://..."],
        }

        # Set multiple vars
        assert parse_cli_args(("myapp", "FOO=bar", "BAZ=qux", "DEBUG=true"), spec) == {
            "app_name": "myapp",
            "settings": ["FOO=bar", "BAZ=qux", "DEBUG=true"],
        }

    def test_real_world_config_get(self):
        """Test realistic config:get command (positional + single remaining)."""
        spec = {
            "app_name": {"positional": True},
            "keys": {"remaining": True},
        }

        result = parse_cli_args(("myapp", "DATABASE_URL"), spec)
        assert result == {"app_name": "myapp", "keys": ["DATABASE_URL"]}
        # For config:get, we'd use keys[0] if available


# ---- L10: a named value-option accepts a value starting with '-' ------------


def test_value_option_accepts_leading_dash_value():
    """`--grep -foo` searches for "-foo"; the value must not be lost/misread."""
    spec = {"grep": {"type": str, "default": ""}}
    result = parse_cli_args(("--grep", "-foo"), spec)
    assert result["grep"] == "-foo"


def test_value_option_at_end_without_value_keeps_default():
    spec = {"grep": {"type": str, "default": "x"}}
    result = parse_cli_args(("--grep",), spec)
    assert result["grep"] == "x"


def test_flag_before_value_option_value_still_parses():
    """A real flag is still a flag; only named value-options eat the next token."""
    spec = {"verbose": {"flag": True}, "grep": {"type": str, "default": ""}}
    result = parse_cli_args(("--verbose", "--grep", "-x"), spec)
    assert result["verbose"] is True
    assert result["grep"] == "-x"


# ---- C9: reject_extra_args fails loud on leftover tokens --------------------


def test_reject_extra_args_raises_on_leftovers():
    with pytest.raises(ValueError, match="Unrecognized argument"):
        reject_extra_args(["--no-addon"])  # the singular typo must not be ignored


def test_reject_extra_args_accepts_empty():
    reject_extra_args([])  # no raise
    reject_extra_args(())  # no raise
