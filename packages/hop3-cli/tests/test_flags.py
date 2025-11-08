# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for CLI flag parsing."""

from __future__ import annotations

from hop3_cli.flags import CliFlags, parse_flags


def test_parse_flags_no_flags():
    """Test parsing with no flags."""
    flags, args = parse_flags(["deploy", "my-app"])
    assert flags == CliFlags(
        json_output=False,
        quiet=False,
        skip_confirm=False,
        verbose=False,
    )
    assert args == ["deploy", "my-app"]


def test_parse_flags_json_flag():
    """Test parsing --json and -j flags."""
    # --json flag
    flags, args = parse_flags(["deploy", "my-app", "--json"])
    assert flags.json_output is True
    assert args == ["deploy", "my-app"]

    # -j flag
    flags, args = parse_flags(["deploy", "my-app", "-j"])
    assert flags.json_output is True
    assert args == ["deploy", "my-app"]

    # Flag at beginning
    flags, args = parse_flags(["--json", "deploy", "my-app"])
    assert flags.json_output is True
    assert args == ["deploy", "my-app"]


def test_parse_flags_quiet_flag():
    """Test parsing --quiet and -q flags."""
    # --quiet flag
    flags, args = parse_flags(["deploy", "my-app", "--quiet"])
    assert flags.quiet is True
    assert args == ["deploy", "my-app"]

    # -q flag
    flags, args = parse_flags(["deploy", "my-app", "-q"])
    assert flags.quiet is True
    assert args == ["deploy", "my-app"]


def test_parse_flags_skip_confirm_flags():
    """Test parsing -y, --yes, and --force flags."""
    # -y flag
    flags, args = parse_flags(["destroy", "my-app", "-y"])
    assert flags.skip_confirm is True
    assert args == ["destroy", "my-app"]

    # --yes flag
    flags, args = parse_flags(["destroy", "my-app", "--yes"])
    assert flags.skip_confirm is True
    assert args == ["destroy", "my-app"]

    # --force flag
    flags, args = parse_flags(["destroy", "my-app", "--force"])
    assert flags.skip_confirm is True
    assert args == ["destroy", "my-app"]


def test_parse_flags_verbose_flag():
    """Test parsing -v and --verbose flags."""
    # -v flag
    flags, args = parse_flags(["deploy", "my-app", "-v"])
    assert flags.verbose is True
    assert args == ["deploy", "my-app"]

    # --verbose flag
    flags, args = parse_flags(["deploy", "my-app", "--verbose"])
    assert flags.verbose is True
    assert args == ["deploy", "my-app"]


def test_parse_flags_multiple_flags():
    """Test parsing multiple flags at once."""
    # JSON + quiet
    flags, args = parse_flags(["deploy", "my-app", "--json", "--quiet"])
    assert flags.json_output is True
    assert flags.quiet is True
    assert flags.skip_confirm is False
    assert flags.verbose is False
    assert args == ["deploy", "my-app"]

    # All flags with short forms
    flags, args = parse_flags(["destroy", "my-app", "-j", "-q", "-y", "-v"])
    assert flags.json_output is True
    assert flags.quiet is True
    assert flags.skip_confirm is True
    assert flags.verbose is True
    assert args == ["destroy", "my-app"]

    # Flags interspersed with args
    flags, args = parse_flags(["-j", "deploy", "-y", "my-app", "--quiet"])
    assert flags.json_output is True
    assert flags.skip_confirm is True
    assert flags.quiet is True
    assert args == ["deploy", "my-app"]


def test_parse_flags_empty_args():
    """Test parsing with empty arguments."""
    flags, args = parse_flags([])
    assert flags == CliFlags(
        json_output=False,
        quiet=False,
        skip_confirm=False,
        verbose=False,
    )
    assert args == []


def test_parse_flags_only_flags():
    """Test parsing with only flags, no command."""
    flags, args = parse_flags(["--json", "-y"])
    assert flags.json_output is True
    assert flags.skip_confirm is True
    assert args == []


def test_parse_flags_duplicate_flags():
    """Test parsing with duplicate flags (last one wins behavior)."""
    # Multiple --json flags (idempotent)
    flags, args = parse_flags(["deploy", "--json", "--json"])
    assert flags.json_output is True
    assert args == ["deploy"]

    # Mix of long and short forms
    flags, args = parse_flags(["deploy", "-j", "--json"])
    assert flags.json_output is True
    assert args == ["deploy"]


def test_parse_flags_preserves_arg_order():
    """Test that argument order is preserved after flag removal."""
    flags, args = parse_flags(["deploy", "my-app", "/path/to/dir", "--json"])
    assert args == ["deploy", "my-app", "/path/to/dir"]

    flags, args = parse_flags(["-y", "destroy", "--quiet", "app1", "app2"])
    assert args == ["destroy", "app1", "app2"]


def test_parse_flags_with_subcommands():
    """Test flag parsing with colon-based subcommands."""
    flags, args = parse_flags(["app:destroy", "my-app", "-y"])
    assert flags.skip_confirm is True
    assert args == ["app:destroy", "my-app"]

    flags, args = parse_flags(["backup:delete", "backup-id", "--json"])
    assert flags.json_output is True
    assert args == ["backup:delete", "backup-id"]


def test_cli_flags_immutability():
    """Test that CliFlags is immutable (frozen dataclass)."""
    flags = CliFlags(json_output=True, quiet=False, skip_confirm=False, verbose=False)

    # Attempting to modify should raise an error
    try:
        flags.json_output = False  # type: ignore
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        # Expected - frozen dataclass prevents modification
        pass


def test_cli_flags_defaults():
    """Test CliFlags default values."""
    flags = CliFlags()
    assert flags.json_output is False
    assert flags.quiet is False
    assert flags.skip_confirm is False
    assert flags.verbose is False
