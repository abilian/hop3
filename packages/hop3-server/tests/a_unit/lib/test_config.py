# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the environment/file Config loader (adapted from Starlette)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hop3.lib.config import (
    Config,
    Environ,
    EnvironError,
    Undefined,
)


class TestEnviron:
    """Tests for the read-once-protected os.environ wrapper."""

    def test_set_and_get_value(self):
        env = Environ({})

        env["FOO"] = "bar"

        assert env["FOO"] == "bar"

    def test_getitem_records_key_as_read(self):
        backing = {"FOO": "bar"}
        env = Environ(backing)

        _ = env["FOO"]

        assert "FOO" in env._has_been_read

    def test_set_after_read_raises(self):
        backing = {"FOO": "bar"}
        env = Environ(backing)
        _ = env["FOO"]

        with pytest.raises(EnvironError) as exc_info:
            env["FOO"] = "baz"

        assert "has already been read" in str(exc_info.value)
        assert backing["FOO"] == "bar"

    def test_set_before_read_is_allowed(self):
        backing = {"FOO": "bar"}
        env = Environ(backing)

        env["FOO"] = "baz"

        assert backing["FOO"] == "baz"

    def test_delete_after_read_raises(self):
        backing = {"FOO": "bar"}
        env = Environ(backing)
        _ = env["FOO"]

        with pytest.raises(EnvironError) as exc_info:
            del env["FOO"]

        assert "has already been read" in str(exc_info.value)
        assert "FOO" in backing

    def test_delete_before_read_is_allowed(self):
        backing = {"FOO": "bar"}
        env = Environ(backing)

        del env["FOO"]

        assert "FOO" not in backing

    def test_iter_yields_backing_keys(self):
        env = Environ({"A": "1", "B": "2"})

        assert sorted(env) == ["A", "B"]

    def test_len_reflects_backing(self):
        env = Environ({"A": "1", "B": "2"})

        assert len(env) == 2

    def test_contains_marks_key_as_read(self):
        # MutableMapping.__contains__ probes via __getitem__, which records
        # the key as read and therefore locks it against later mutation.
        env = Environ({"FOO": "bar"})

        assert "FOO" in env

        with pytest.raises(EnvironError):
            env["FOO"] = "baz"


class TestConfigFromEnviron:
    """Tests for Config reading from an environ mapping."""

    def test_returns_value_present_in_environ(self):
        config = Config(environ={"KEY": "value"})

        assert config("KEY") == "value"

    def test_call_delegates_to_get(self):
        config = Config(environ={"KEY": "value"})

        assert config("KEY") == config.get("KEY")

    def test_missing_key_without_default_raises_keyerror(self):
        config = Config(environ={})

        with pytest.raises(KeyError) as exc_info:
            config("MISSING")

        assert "is missing, and has no default" in str(exc_info.value)

    def test_missing_key_returns_default(self):
        config = Config(environ={})

        assert config("MISSING", default="fallback") == "fallback"

    def test_none_default_is_returned(self):
        config = Config(environ={})

        assert config("MISSING", default=None) is None

    def test_environ_takes_precedence_over_default(self):
        config = Config(environ={"KEY": "env"})

        assert config("KEY", default="fallback") == "env"


class TestConfigEnvPrefix:
    """Tests for env_prefix handling."""

    def test_prefix_is_prepended_to_lookup(self):
        config = Config(environ={"APP_KEY": "value"}, env_prefix="APP_")

        assert config("KEY") == "value"

    def test_unprefixed_key_is_not_found(self):
        config = Config(environ={"KEY": "value"}, env_prefix="APP_")

        with pytest.raises(KeyError):
            config("KEY")


class TestPerformCast:
    """Tests for the _perform_cast value-conversion logic."""

    def test_no_cast_returns_value_unchanged(self):
        config = Config(environ={"KEY": "raw"})

        assert config("KEY") == "raw"

    def test_none_value_with_cast_returns_none(self):
        config = Config(environ={})

        # default None short-circuits the cast even when a cast is given.
        assert config("MISSING", cast=int, default=None) is None

    def test_int_cast(self):
        config = Config(environ={"KEY": "42"})

        assert config("KEY", cast=int) == 42

    def test_float_cast(self):
        config = Config(environ={"KEY": "3.5"})

        assert config("KEY", cast=float) == 3.5

    def test_invalid_int_cast_raises_value_error(self):
        config = Config(environ={"KEY": "not-an-int"})

        with pytest.raises(ValueError) as exc_info:
            config("KEY", cast=int)

        assert "Not a valid int" in str(exc_info.value)

    def test_cast_error_message_includes_key_and_value(self):
        config = Config(environ={"PORT": "abc"})

        with pytest.raises(ValueError) as exc_info:
            config("PORT", cast=int)

        message = str(exc_info.value)
        assert "PORT" in message
        assert "abc" in message

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("false", False),
            ("False", False),
            ("0", False),
        ],
    )
    def test_bool_cast_valid_values(self, raw, expected):
        config = Config(environ={"FLAG": raw})

        assert config("FLAG", cast=bool) is expected

    def test_invalid_bool_cast_raises_value_error(self):
        config = Config(environ={"FLAG": "maybe"})

        with pytest.raises(ValueError) as exc_info:
            config("FLAG", cast=bool)

        assert "Not a valid bool" in str(exc_info.value)

    def test_bool_cast_on_non_string_uses_builtin_bool(self):
        # A non-str default with bool cast bypasses the string mapping.
        config = Config(environ={})

        assert config("MISSING", cast=bool, default=0) is False
        assert config("MISSING", cast=bool, default=[1]) is True

    def test_callable_cast(self):
        config = Config(environ={"KEY": "abc"})

        assert config("KEY", cast=str.upper) == "ABC"

    def test_cast_applies_to_default(self):
        config = Config(environ={})

        assert config("MISSING", cast=int, default="7") == 7


class TestTypedGetters:
    """Tests for the get_<type> convenience helpers."""

    def test_get_str(self):
        config = Config(environ={"KEY": "value"})

        assert config.get_str("KEY") == "value"

    def test_get_int(self):
        config = Config(environ={"KEY": "10"})

        assert config.get_int("KEY") == 10

    def test_get_float(self):
        config = Config(environ={"KEY": "2.5"})

        assert config.get_float("KEY") == 2.5

    def test_get_bool(self):
        config = Config(environ={"KEY": "true"})

        assert config.get_bool("KEY") is True

    def test_get_path_returns_path_object(self):
        config = Config(environ={"KEY": "/tmp/x"})

        result = config.get_path("KEY")

        assert isinstance(result, Path)
        assert result == Path("/tmp/x")

    def test_typed_getter_uses_default(self):
        config = Config(environ={})

        assert config.get_int("MISSING", default=99) == 99


class TestConfigFromFile:
    """Tests for loading values from a TOML file."""

    def test_reads_value_from_file(self, tmp_path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('key = "value"\n')
        config = Config(file=toml_file)

        # Keys from file are upper-cased on load.
        assert config("KEY") == "value"

    def test_file_keys_are_uppercased(self, tmp_path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('Lower_Case = "v"\n')
        config = Config(file=toml_file)

        assert config("LOWER_CASE") == "v"
        with pytest.raises(KeyError):
            config("Lower_Case")

    def test_environ_takes_precedence_over_file(self, tmp_path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('key = "file"\n')
        config = Config(environ={"KEY": "env"}, file=toml_file)

        assert config("KEY") == "env"

    def test_file_value_used_when_not_in_environ(self, tmp_path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('only_in_file = "f"\n')
        config = Config(environ={}, file=toml_file)

        assert config("ONLY_IN_FILE") == "f"

    def test_default_used_when_absent_from_environ_and_file(self, tmp_path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('key = "file"\n')
        config = Config(environ={}, file=toml_file)

        assert config("OTHER", default="d") == "d"

    def test_non_toml_suffix_raises_assertion(self, tmp_path):
        bad_file = tmp_path / "config.ini"
        bad_file.write_text("key = value\n")

        with pytest.raises(AssertionError):
            Config(file=bad_file)

    def test_no_file_means_empty_file_values(self):
        config = Config(environ={})

        assert config.file_values == {}


class TestUndefinedSentinel:
    """Tests for the Undefined sentinel used to distinguish 'no default'."""

    def test_undefined_is_used_as_missing_marker(self):
        # An explicit Undefined default behaves like passing no default.
        config = Config(environ={})

        with pytest.raises(KeyError):
            config("MISSING", default=Undefined)
