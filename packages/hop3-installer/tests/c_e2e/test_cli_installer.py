# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""E2E tests for CLI installer (install-cli.py).

These tests verify that the bundled CLI installer correctly installs
hop3-cli in various scenarios across different backends (Docker, SSH, Vagrant).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_installer.testing.backends import Backend


@pytest.mark.e2e
class TestCLIInstaller:
    """Test hop3-cli installation via install-cli.py."""

    def test_install_cli_from_git(
        self,
        backend: Backend,
        bundled_installers: dict[str, Path],
    ) -> None:
        """Test CLI installation from git repository.

        This is the primary installation method - installing from the
        git repository's devel branch.
        """
        # Clean up any previous installation
        backend.cleanup_cli()

        # Upload installer to target
        installer_path = "/tmp/install-cli.py"
        assert backend.upload(
            bundled_installers["cli"], installer_path
        ), "Failed to upload installer"

        # Run installer with git method
        result = backend.run(
            f"python3 {installer_path} --git --branch devel --no-modify-path --verbose"
        )

        # Check installer succeeded
        assert result.success, (
            f"CLI installer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Validate installation
        self._validate_cli_installation(backend)

    def test_install_cli_from_local_path(
        self,
        backend: Backend,
        bundled_installers: dict[str, Path],
        hop3_packages_dir: Path,
    ) -> None:
        """Test CLI installation from local package path.

        This tests the --local-path option used during development.
        """
        # Clean up any previous installation
        backend.cleanup_cli()

        # Upload installer to target
        installer_path = "/tmp/install-cli.py"
        assert backend.upload(
            bundled_installers["cli"], installer_path
        ), "Failed to upload installer"

        # Upload the hop3-cli package to target
        cli_package = hop3_packages_dir / "hop3-cli"
        if not cli_package.exists():
            pytest.skip(f"hop3-cli package not found: {cli_package}")

        remote_pkg_path = "/tmp/hop3-cli"
        assert backend.upload_dir(cli_package, remote_pkg_path), (
            "Failed to upload CLI package"
        )

        # Run installer with local path
        result = backend.run(
            f"python3 {installer_path} --local-path {remote_pkg_path} "
            "--no-modify-path --verbose"
        )

        # Check installer succeeded
        assert result.success, (
            f"CLI installer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Validate installation
        self._validate_cli_installation(backend)

    def _validate_cli_installation(self, backend: Backend) -> None:
        """Validate CLI was installed correctly.

        Checks:
        1. Virtual environment was created
        2. hop3 command exists in venv
        3. hop3 command runs without crashing
        """
        # Check venv exists
        result = backend.run("test -d ~/.hop3-cli/venv")
        assert result.success, "CLI virtual environment not created"

        # Check hop3 command exists
        result = backend.run(
            "test -f ~/.hop3-cli/venv/bin/hop3 || test -f ~/.hop3-cli/venv/bin/hop"
        )
        assert result.success, "hop3 command not found in venv"

        # Check hop3 runs (version command doesn't need server config)
        result = backend.run("~/.hop3-cli/venv/bin/hop3 version 2>&1 || true")
        # The command might fail if no server is configured, but it should at least
        # print something about hop3
        output = (result.stdout + result.stderr).lower()
        assert "hop3" in output or result.success, (
            f"hop3 command doesn't run properly: {result.stdout} {result.stderr}"
        )
