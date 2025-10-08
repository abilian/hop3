# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for --help flag handling."""

from __future__ import annotations

from hop3_cli.main import handle_help_flags


def test_help_flags_basic():
    """Test basic --help flag handling."""
    # Just --help
    assert handle_help_flags(["--help"]) == ["help"]
    assert handle_help_flags(["-h"]) == ["help"]

    # Command with --help
    assert handle_help_flags(["run", "--help"]) == ["help", "run"]
    assert handle_help_flags(["run", "-h"]) == ["help", "run"]

    # Command with arguments and --help
    assert handle_help_flags(["run", "myapp", "--help"]) == ["help", "run"]
    assert handle_help_flags(["deploy", "app", "--help"]) == ["help", "deploy"]

    # No --help flag
    assert handle_help_flags(["run", "myapp"]) == ["run", "myapp"]
    assert handle_help_flags(["deploy"]) == ["deploy"]

    # Empty args
    assert handle_help_flags([]) == []


def test_help_flags_with_subcommands():
    """Test --help with subcommands."""
    assert handle_help_flags(["config:show", "--help"]) == ["help", "config:show"]
    assert handle_help_flags(["app:status", "-h"]) == ["help", "app:status"]
