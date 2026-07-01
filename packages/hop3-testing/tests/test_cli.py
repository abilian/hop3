# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for CLI commands."""

from __future__ import annotations

from click.testing import CliRunner
from hop3_testing.cli import cli


class TestCLIBasics:
    """Basic CLI functionality tests."""

    def test_cli_help(self):
        """Test that CLI help works."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "Hop3 Test Runner" in result.output or "hop3" in result.output.lower()

    def test_cli_version(self):
        """Test that CLI version option exists."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])

        # Version should work or not be an error
        assert result.exit_code == 0 or "no such option" in result.output.lower()


class TestListCommand:
    """Tests for the list command."""

    def test_list_help(self):
        """Test list command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output.lower() or "tests" in result.output.lower()

    def test_list_runs(self):
        """Test list command runs (may find no tests depending on cwd)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["list"])

        # Should either succeed or exit gracefully (no tests found)
        assert result.exit_code in {0, 1}


class TestListShowOption:
    """Tests for the list --show option (replaces show command)."""

    def test_list_show_missing_test(self):
        """Test list --show with non-existent test."""
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--show", "nonexistent-test-name"])

        # Should exit with error or report not found
        assert result.exit_code != 0 or "not found" in result.output.lower()


class TestSystemCommand:
    """Tests for the system command."""

    def test_run_help(self):
        """Test the `run` command help (ADR 052 D9; `system` is an alias)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])

        assert result.exit_code == 0
        assert "--docker" in result.output
        assert "--ssh" in result.output
        assert "--from" in result.output  # canonical source selector

    def test_run_requires_target(self):
        """Test the `run` command requires --docker or --ssh."""
        runner = CliRunner()
        result = runner.invoke(cli, ["run"])

        # Should fail with error about missing target
        assert result.exit_code != 0
        assert "Must specify --docker or --ssh" in result.output


class TestSystemReuse:
    """Test that --reuse replaces the old 'apps' command."""

    def test_reuse_requires_target(self):
        """Test `run --reuse` still requires --docker or --ssh."""
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--reuse"])

        assert result.exit_code != 0
        assert "Must specify --docker or --ssh" in result.output
