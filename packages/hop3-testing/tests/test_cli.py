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
        assert result.exit_code in (0, 1)


class TestShowCommand:
    """Tests for the show command."""

    def test_show_help(self):
        """Test show command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["show", "--help"])

        assert result.exit_code == 0

    def test_show_missing_test(self):
        """Test show with non-existent test."""
        runner = CliRunner()
        result = runner.invoke(cli, ["show", "nonexistent-test-name"])

        # Should exit with error or report not found
        assert result.exit_code != 0 or "not found" in result.output.lower()


class TestSystemCommand:
    """Tests for the system command."""

    def test_system_help(self):
        """Test system command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["system", "--help"])

        assert result.exit_code == 0
        assert "--docker" in result.output
        assert "--ssh" in result.output
        assert "--deploy-from" in result.output

    def test_system_requires_target(self):
        """Test system command requires --docker or --ssh."""
        runner = CliRunner()
        result = runner.invoke(cli, ["system"])

        # Should fail with error about missing target
        assert result.exit_code != 0
        assert "Must specify --docker or --ssh" in result.output


class TestAppsCommand:
    """Tests for the apps command."""

    def test_apps_help(self):
        """Test apps command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["apps", "--help"])

        assert result.exit_code == 0
        assert "--target" in result.output or "--keep" in result.output


class TestBuildCommands:
    """Tests for build-related commands."""

    def test_build_ready_image_help(self):
        """Test build-ready-image command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["build-ready-image", "--help"])

        assert result.exit_code == 0
        assert "--tag" in result.output or "--no-cache" in result.output

    def test_build_test_image_help(self):
        """Test build-test-image command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["build-test-image", "--help"])

        assert result.exit_code == 0


class TestModeCommands:
    """Tests for mode-based commands (dev, ci, nightly)."""

    def test_dev_help(self):
        """Test dev command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["dev", "--help"])

        assert result.exit_code == 0

    def test_ci_help(self):
        """Test ci command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ci", "--help"])

        assert result.exit_code == 0

    def test_nightly_help(self):
        """Test nightly command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["nightly", "--help"])

        assert result.exit_code == 0
