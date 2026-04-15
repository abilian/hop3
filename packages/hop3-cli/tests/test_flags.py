# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for CLI flag parsing."""

from __future__ import annotations

from hop3_cli.commands.flags import CliFlags, parse_flags


def test_parse_flags_no_flags():
    """Test parsing with no flags."""
    flags, args = parse_flags(["deploy", "my-app"])
    assert flags.json_output is False
    assert flags.skip_confirm is False
    assert flags.verbosity == 1  # normal
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
    assert flags.verbosity == 0
    assert args == ["deploy", "my-app"]

    # -q flag
    flags, args = parse_flags(["deploy", "my-app", "-q"])
    assert flags.quiet is True
    assert flags.verbosity == 0
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
    assert flags.verbosity == 2
    assert args == ["deploy", "my-app"]

    # --verbose flag
    flags, args = parse_flags(["deploy", "my-app", "--verbose"])
    assert flags.verbose is True
    assert flags.verbosity == 2
    assert args == ["deploy", "my-app"]


def test_parse_flags_multiple_v():
    """Test parsing multiple -v flags (-vv, -vvv)."""
    # -vv flag
    flags, args = parse_flags(["deploy", "my-app", "-vv"])
    assert flags.verbosity == 3  # debug level
    assert flags.debug is True
    assert args == ["deploy", "my-app"]

    # -vvv flag (caps at 3)
    flags, args = parse_flags(["deploy", "my-app", "-vvv"])
    assert flags.verbosity == 3
    assert args == ["deploy", "my-app"]


def test_parse_flags_debug_flag():
    """Test parsing --debug flag."""
    flags, args = parse_flags(["deploy", "my-app", "--debug"])
    assert flags.debug is True
    assert flags.verbosity == 3
    assert args == ["deploy", "my-app"]


def test_parse_flags_multiple_flags():
    """Test parsing multiple flags at once."""
    # JSON + quiet
    flags, args = parse_flags(["deploy", "my-app", "--json", "--quiet"])
    assert flags.json_output is True
    assert flags.quiet is True
    assert flags.skip_confirm is False
    assert args == ["deploy", "my-app"]

    # All flags with short forms
    flags, args = parse_flags(["destroy", "my-app", "-j", "-q", "-y", "-v"])
    assert flags.json_output is True
    # Note: -q sets verbosity=0, -v sets verbosity=2, last one processed wins
    # Actually in our implementation, -q comes before -v so -v takes effect
    assert flags.skip_confirm is True
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
    assert flags.json_output is False
    assert flags.skip_confirm is False
    assert flags.verbosity == 1
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
    assert flags.skip_confirm is True
    assert flags.quiet is True
    assert args == ["destroy", "app1", "app2"]


def test_parse_flags_with_subcommands():
    """Test flag parsing with colon-based subcommands."""
    flags, args = parse_flags(["app", "destroy", "my-app", "-y"])
    assert flags.skip_confirm is True
    assert args == ["app", "destroy", "my-app"]

    flags, args = parse_flags(["backup", "destroy", "backup-id", "--json"])
    assert flags.json_output is True
    assert args == ["backup", "destroy", "backup-id"]


def test_cli_flags_immutability():
    """Test that CliFlags is immutable (frozen dataclass)."""
    flags = CliFlags(json_output=True, skip_confirm=False, verbosity=1)

    # Attempting to modify should raise an error
    try:
        flags.json_output = False  # type: ignore
        msg = "Should have raised FrozenInstanceError"
        raise AssertionError(msg)
    except AttributeError:
        # Expected - frozen dataclass prevents modification
        pass


def test_cli_flags_defaults():
    """Test CliFlags default values."""
    flags = CliFlags()
    assert flags.json_output is False
    assert flags.skip_confirm is False
    assert flags.verbosity == 1
    assert flags.quiet is False
    assert flags.verbose is False
    assert flags.debug is False


def test_cli_flags_verbosity_properties():
    """Test CliFlags verbosity-derived properties."""
    # Quiet (verbosity=0)
    flags = CliFlags(verbosity=0)
    assert flags.quiet is True
    assert flags.verbose is False
    assert flags.debug is False

    # Normal (verbosity=1)
    flags = CliFlags(verbosity=1)
    assert flags.quiet is False
    assert flags.verbose is False
    assert flags.debug is False

    # Verbose (verbosity=2)
    flags = CliFlags(verbosity=2)
    assert flags.quiet is False
    assert flags.verbose is True
    assert flags.debug is False

    # Debug (verbosity=3)
    flags = CliFlags(verbosity=3)
    assert flags.quiet is False
    assert flags.verbose is True
    assert flags.debug is True


def test_parse_flags_app_long():
    """Test --app <name> flag (ADR 036 D5)."""
    flags, args = parse_flags(["deploy", "--app", "myapp"])
    assert flags.app == "myapp"
    assert args == ["deploy"]


def test_parse_flags_app_short():
    """Test -a <name> short form for --app."""
    flags, args = parse_flags(["logs", "-a", "myapp", "--follow"])
    assert flags.app == "myapp"
    assert args == ["logs", "--follow"]


def test_parse_flags_context_short():
    """Test -c <name> short form for --context."""
    flags, args = parse_flags(["deploy", "-c", "prod"])
    assert flags.context == "prod"
    assert args == ["deploy"]


def test_parse_flags_why():
    """Test --why flag for resolution trace."""
    flags, args = parse_flags(["logs", "--why"])
    assert flags.why is True
    assert args == ["logs"]


def test_parse_flags_no_alias():
    """Test --no-alias flag."""
    flags, args = parse_flags(["apps", "--no-alias"])
    assert flags.no_alias is True
    assert args == ["apps"]


def test_parse_flags_app_defaults_to_none():
    flags, _ = parse_flags(["deploy"])
    assert flags.app is None


def test_parse_flags_combined():
    """Test combining several of the new flags."""
    flags, args = parse_flags(["config", "set", "-a", "myapp", "-c", "prod", "FOO=bar"])
    assert flags.app == "myapp"
    assert flags.context == "prod"
    assert args == ["config", "set", "FOO=bar"]
