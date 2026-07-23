# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the settings file parser and writer."""

from __future__ import annotations

import pytest

from hop3.lib.settings import parse_settings, write_settings


class TestWriteSettings:
    """Tests for write_settings."""

    def test_writes_key_value_pairs(self, tmp_path):
        """write_settings emits one KEY=VALUE line per entry."""
        target = tmp_path / "settings.env"

        write_settings(target, {"FOO": "bar", "BAZ": "qux"})

        assert target.read_text() == "BAZ=qux\nFOO=bar\n"

    def test_sorts_keys_alphabetically(self, tmp_path):
        """Entries are written sorted by key, independent of insertion order."""
        target = tmp_path / "settings.env"

        write_settings(target, {"ZED": "1", "ALPHA": "2", "MID": "3"})

        assert target.read_text() == "ALPHA=2\nMID=3\nZED=1\n"

    def test_empty_bag_creates_empty_file(self, tmp_path):
        """An empty mapping produces an empty (but existing) file."""
        target = tmp_path / "settings.env"

        write_settings(target, {})

        assert target.exists()
        assert target.read_text() == ""

    def test_creates_missing_parent_directories(self, tmp_path):
        """Parent directories are created when they do not yet exist."""
        target = tmp_path / "deep" / "nested" / "settings.env"

        write_settings(target, {"KEY": "value"})

        assert target.read_text() == "KEY=value\n"

    def test_custom_separator(self, tmp_path):
        """A custom separator is used between key and value."""
        target = tmp_path / "settings.cfg"

        write_settings(target, {"KEY": "value"}, separator=": ")

        assert target.read_text() == "KEY: value\n"

    def test_accepts_string_path(self, tmp_path):
        """A str path is accepted as well as a Path object."""
        target = tmp_path / "settings.env"

        write_settings(str(target), {"KEY": "value"})

        assert target.read_text() == "KEY=value\n"

    def test_stringifies_non_string_values(self, tmp_path):
        """Non-string values are rendered via str()."""
        target = tmp_path / "settings.env"

        write_settings(target, {"PORT": 8080, "RATIO": 1.5})

        assert target.read_text() == "PORT=8080\nRATIO=1.5\n"

    def test_overwrites_existing_file(self, tmp_path):
        """Writing replaces any prior file contents."""
        target = tmp_path / "settings.env"
        target.write_text("STALE=old\nMORE=lines\n")

        write_settings(target, {"FRESH": "new"})

        assert target.read_text() == "FRESH=new\n"


class TestParseSettings:
    """Tests for parse_settings."""

    def test_parses_key_value_pairs(self, tmp_path):
        """A simple settings file is parsed into a dict."""
        target = tmp_path / "settings.env"
        target.write_text("FOO=bar\nBAZ=qux\n")

        result = parse_settings(target)

        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_missing_file_returns_empty_dict(self, tmp_path):
        """A non-existent file yields an empty dict."""
        target = tmp_path / "does_not_exist.env"

        assert parse_settings(target) == {}

    def test_missing_file_ignores_provided_env(self, tmp_path):
        """A missing file returns {} without leaking the passed-in env."""
        target = tmp_path / "does_not_exist.env"

        result = parse_settings(target, env={"PRE": "existing"})

        assert result == {}

    def test_strips_whitespace_around_key_and_value(self, tmp_path):
        """Surrounding whitespace on key and value is stripped."""
        target = tmp_path / "settings.env"
        target.write_text("  FOO  =  bar  \n")

        result = parse_settings(target)

        assert result == {"FOO": "bar"}

    def test_skips_comment_lines(self, tmp_path):
        """Lines beginning with '#' are ignored."""
        target = tmp_path / "settings.env"
        target.write_text("# a comment\nFOO=bar\n# another\n")

        result = parse_settings(target)

        assert result == {"FOO": "bar"}

    def test_skips_blank_and_whitespace_only_lines(self, tmp_path):
        """Empty and whitespace-only lines are ignored."""
        target = tmp_path / "settings.env"
        target.write_text("FOO=bar\n\n   \n\t\nBAZ=qux\n")

        result = parse_settings(target)

        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_value_may_contain_equals_sign(self, tmp_path):
        """Only the first '=' splits the line; later ones stay in the value."""
        target = tmp_path / "settings.env"
        target.write_text("DSN=postgres://u:p@h/db?a=1&b=2\n")

        result = parse_settings(target)

        assert result == {"DSN": "postgres://u:p@h/db?a=1&b=2"}

    def test_empty_value(self, tmp_path):
        """A key with no value parses to an empty string."""
        target = tmp_path / "settings.env"
        target.write_text("EMPTY=\n")

        result = parse_settings(target)

        assert result == {"EMPTY": ""}

    def test_later_key_overrides_earlier(self, tmp_path):
        """A duplicated key keeps the last value seen."""
        target = tmp_path / "settings.env"
        target.write_text("KEY=first\nKEY=second\n")

        result = parse_settings(target)

        assert result == {"KEY": "second"}

    def test_expands_variable_from_same_file(self, tmp_path):
        """A value referencing an earlier key is expanded from accumulated env."""
        target = tmp_path / "settings.env"
        target.write_text("BASE=/srv\nFULL=${BASE}/app\n")

        result = parse_settings(target)

        assert result == {"BASE": "/srv", "FULL": "/srv/app"}

    def test_expands_variable_from_provided_env(self, tmp_path):
        """A value referencing a pre-supplied env var is expanded."""
        target = tmp_path / "settings.env"
        target.write_text("PATHED=${HOME}/bin\n")

        result = parse_settings(target, env={"HOME": "/home/user"})

        assert result == {"HOME": "/home/user", "PATHED": "/home/user/bin"}

    def test_unknown_variable_left_verbatim(self, tmp_path):
        """An unresolved variable reference is left untouched."""
        target = tmp_path / "settings.env"
        target.write_text("X=${UNDEFINED}\n")

        result = parse_settings(target)

        assert result == {"X": "${UNDEFINED}"}

    def test_mutates_and_returns_provided_env(self, tmp_path):
        """parse_settings updates the supplied env dict in place and returns it."""
        target = tmp_path / "settings.env"
        target.write_text("NEW=value\n")
        env = {"OLD": "kept"}

        result = parse_settings(target, env=env)

        assert result is env
        assert env == {"OLD": "kept", "NEW": "value"}

    def test_malformed_line_raises(self, tmp_path):
        """A line with no '=' fails loud instead of silently discarding the file."""
        target = tmp_path / "settings.env"
        target.write_text("VALID=ok\nthis-line-has-no-equals\n")

        with pytest.raises(ValueError, match="Malformed setting"):
            parse_settings(target)

    def test_malformed_line_raises_even_with_provided_env(self, tmp_path):
        """A malformed line aborts rather than silently dropping the passed env."""
        target = tmp_path / "settings.env"
        target.write_text("malformed\n")

        with pytest.raises(ValueError, match="Malformed setting"):
            parse_settings(target, env={"PRE": "existing"})

    def test_nul_byte_in_expansion_value_raises(self, tmp_path):
        """
        A NUL byte makes expand_vars raise; parse_settings surfaces it loudly
        rather than swallowing the whole file into {}.
        """
        target = tmp_path / "settings.env"
        target.write_text("TARGET=$BAD\n")

        with pytest.raises(ValueError, match="Malformed setting"):
            parse_settings(target, env={"BAD": "x\x00y"})

    def test_accepts_string_path(self, tmp_path):
        """A str path is accepted as well as a Path object."""
        target = tmp_path / "settings.env"
        target.write_text("FOO=bar\n")

        result = parse_settings(str(target))

        assert result == {"FOO": "bar"}

    def test_file_without_trailing_newline(self, tmp_path):
        """A final line lacking a trailing newline is still parsed."""
        target = tmp_path / "settings.env"
        target.write_text("FOO=bar")

        result = parse_settings(target)

        assert result == {"FOO": "bar"}


class TestRoundTrip:
    """write_settings and parse_settings compose."""

    def test_write_then_parse_recovers_values(self, tmp_path):
        """Values written out are recovered verbatim by the parser."""
        target = tmp_path / "settings.env"
        bag = {"ALPHA": "1", "BETA": "two", "GAMMA": "three"}

        write_settings(target, bag)
        result = parse_settings(target)

        assert result == bag
