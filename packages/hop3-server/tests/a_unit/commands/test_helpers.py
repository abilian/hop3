# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for command helper functions."""

from __future__ import annotations

from unittest.mock import MagicMock

from hop3.commands._helpers import (
    parse_key_value_settings,
    set_env_var,
    unset_env_var,
)


class TestParseKeyValueSettings:
    """Tests for parse_key_value_settings function."""

    def test_single_setting(self):
        settings = ["FOO=bar"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {"FOO": "bar"}
        assert errors == []

    def test_multiple_settings(self):
        settings = ["FOO=bar", "BAZ=qux", "DEBUG=true"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {"FOO": "bar", "BAZ": "qux", "DEBUG": "true"}
        assert errors == []

    def test_value_with_equals_sign(self):
        settings = ["DATABASE_URL=postgres://user:pass@host/db?foo=bar"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {"DATABASE_URL": "postgres://user:pass@host/db?foo=bar"}
        assert errors == []

    def test_empty_value(self):
        settings = ["FOO="]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {"FOO": ""}
        assert errors == []

    def test_whitespace_trimmed(self):
        settings = ["  FOO  =  bar  "]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {"FOO": "bar"}
        assert errors == []

    def test_invalid_format_no_equals(self):
        settings = ["FOO"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {}
        assert len(errors) == 1
        assert "Invalid setting format" in errors[0]

    def test_empty_key(self):
        settings = ["=bar"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {}
        assert len(errors) == 1
        assert "Empty key" in errors[0]

    def test_mixed_valid_and_invalid(self):
        settings = ["FOO=bar", "INVALID", "BAZ=qux", "=empty_key"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {"FOO": "bar", "BAZ": "qux"}
        assert len(errors) == 2

    def test_empty_list(self):
        settings = []
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {}
        assert errors == []

    def test_rejects_key_with_shell_metacharacters(self):
        # A key like this would previously be interpolated unquoted into
        # `export {key}='{value}'` inside an `sh -c` string, enabling
        # command injection at deploy time.
        settings = ["FOO;touch /tmp/pwned=bar"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {}
        assert len(errors) == 1
        assert "FOO;touch" in errors[0]

    def test_rejects_key_starting_with_digit(self):
        settings = ["1FOO=bar"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {}
        assert len(errors) == 1

    def test_rejects_key_with_newline(self):
        settings = ["FOO\nBAR=baz"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {}
        assert len(errors) == 1

    def test_rejects_key_with_space(self):
        settings = ["FOO BAR=baz"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {}
        assert len(errors) == 1

    def test_valid_underscored_keys(self):
        settings = ["DATABASE_URL=x", "_PRIVATE=y"]
        parsed, errors = parse_key_value_settings(settings)
        assert parsed == {"DATABASE_URL": "x", "_PRIVATE": "y"}
        assert errors == []


class TestSetEnvVar:
    """Tests for set_env_var function."""

    def test_set_new_variable(self):
        app = MagicMock()
        app.env_vars = []

        result = set_env_var(app, "FOO", "bar")

        assert result == "Set FOO=bar"
        assert len(app.env_vars) == 1

    def test_update_existing_variable(self):
        env_var = MagicMock()
        env_var.name = "FOO"
        env_var.value = "old_value"

        app = MagicMock()
        app.env_vars = [env_var]

        result = set_env_var(app, "FOO", "new_value")

        assert result == "Updated FOO=new_value (was: old_value)"
        assert env_var.value == "new_value"

    def test_set_different_variable(self):
        existing_var = MagicMock()
        existing_var.name = "OTHER"
        existing_var.value = "value"

        app = MagicMock()
        app.env_vars = [existing_var]

        result = set_env_var(app, "FOO", "bar")

        assert result == "Set FOO=bar"
        assert len(app.env_vars) == 2


class TestUnsetEnvVar:
    """Tests for unset_env_var function."""

    def test_unset_existing_variable(self):
        env_var = MagicMock()
        env_var.name = "FOO"

        app = MagicMock()
        app.env_vars = [env_var]

        result = unset_env_var(app, "FOO")

        assert result is True
        assert env_var not in app.env_vars

    def test_unset_nonexistent_variable(self):
        app = MagicMock()
        app.env_vars = []

        result = unset_env_var(app, "FOO")

        assert result is False

    def test_unset_different_variable(self):
        env_var = MagicMock()
        env_var.name = "OTHER"

        app = MagicMock()
        app.env_vars = [env_var]

        result = unset_env_var(app, "FOO")

        assert result is False
        assert env_var in app.env_vars  # Should still be there
