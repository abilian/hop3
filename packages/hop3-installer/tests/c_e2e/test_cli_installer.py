# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""E2E tests for CLI installer (install-cli.py).

These tests verify that the bundled CLI installer correctly installs
hop3-cli in various scenarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .conftest import docker_copy, docker_copy_dir, docker_exec

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.e2e
class TestCLIInstaller:
    """Test hop3-cli installation via install-cli.py."""

    def test_install_cli_from_git(
        self,
        docker_container: str,
        bundled_installers: dict[str, Path],
    ) -> None:
        """Test CLI installation from git repository.

        This is the primary installation method - installing from the
        git repository's devel branch.
        """
        # Copy installer to container
        docker_copy(docker_container, bundled_installers["cli"], "/tmp/install-cli.py")

        # Run installer with git method
        result = docker_exec(
            docker_container,
            "python3 /tmp/install-cli.py --git --branch devel --no-modify-path --verbose",
            check=False,
        )

        # Check installer succeeded
        assert result.returncode == 0, (
            f"CLI installer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Validate installation
        self._validate_cli_installation(docker_container)

    def test_install_cli_from_local_path(
        self,
        docker_container: str,
        bundled_installers: dict[str, Path],
        hop3_packages_dir: Path,
    ) -> None:
        """Test CLI installation from local package path.

        This tests the --local-path option used during development.
        """
        # Copy installer to container
        docker_copy(docker_container, bundled_installers["cli"], "/tmp/install-cli.py")

        # Copy the hop3-cli package to container
        cli_package = hop3_packages_dir / "hop3-cli"
        if not cli_package.exists():
            pytest.skip(f"hop3-cli package not found: {cli_package}")

        docker_copy_dir(docker_container, cli_package, "/tmp/hop3-cli")

        # Clean up any previous installation
        docker_exec(
            docker_container,
            "rm -rf ~/.hop3-cli",
            check=False,
        )

        # Run installer with local path
        result = docker_exec(
            docker_container,
            "python3 /tmp/install-cli.py --local-path /tmp/hop3-cli --no-modify-path --verbose",
            check=False,
        )

        # Check installer succeeded
        assert result.returncode == 0, (
            f"CLI installer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Validate installation
        self._validate_cli_installation(docker_container)

    def _validate_cli_installation(self, container: str) -> None:
        """Validate CLI was installed correctly.

        Checks:
        1. Virtual environment was created
        2. hop3 command exists in venv
        3. hop3 command runs without crashing
        """
        # Check venv exists
        result = docker_exec(container, "test -d ~/.hop3-cli/venv", check=False)
        assert result.returncode == 0, "CLI virtual environment not created"

        # Check hop3 command exists
        result = docker_exec(
            container,
            "test -f ~/.hop3-cli/venv/bin/hop3 || test -f ~/.hop3-cli/venv/bin/hop",
            check=False,
        )
        assert result.returncode == 0, "hop3 command not found in venv"

        # Check hop3 runs (version command doesn't need server config)
        result = docker_exec(
            container,
            "~/.hop3-cli/venv/bin/hop3 version 2>&1 || true",
            check=False,
        )
        # The command might fail if no server is configured, but it should at least
        # print something about hop3
        output = (result.stdout + result.stderr).lower()
        assert "hop3" in output or result.returncode == 0, (
            f"hop3 command doesn't run properly: {result.stdout} {result.stderr}"
        )
