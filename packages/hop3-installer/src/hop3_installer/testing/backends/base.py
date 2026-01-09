# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Abstract base class for test backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_installer.testing.common import CommandResult


class Backend(ABC):
    """Abstract base class for test execution backends.

    A backend provides an environment for running installer tests.
    Implementations include SSH (remote servers), Docker (containers),
    and Vagrant (virtual machines).
    """

    # Backend name for display
    name: str = "base"

    # Whether this backend supports full systemd testing
    supports_systemd: bool = False

    @abstractmethod
    def setup(self) -> bool:
        """Set up the test environment.

        This should start containers/VMs, verify SSH connections, etc.

        Returns:
            True if setup succeeded, False otherwise.
        """

    @abstractmethod
    def teardown(self) -> None:
        """Clean up the test environment.

        This should stop containers/VMs, clean up resources, etc.
        """

    @abstractmethod
    def run(self, command: str, *, sudo: bool = False) -> CommandResult:
        """Run a command in the test environment.

        Args:
            command: The command to execute
            sudo: Whether to run with sudo privileges

        Returns:
            CommandResult with returncode, stdout, and stderr
        """

    @abstractmethod
    def upload(self, local_path: Path, remote_path: str) -> bool:
        """Upload a file to the test environment.

        Args:
            local_path: Local file path
            remote_path: Remote destination path

        Returns:
            True if upload succeeded, False otherwise.
        """

    @abstractmethod
    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """Upload a directory to the test environment.

        Args:
            local_path: Local directory path
            remote_path: Remote destination path

        Returns:
            True if upload succeeded, False otherwise.
        """

    @abstractmethod
    def cleanup_cli(self) -> None:
        """Clean up CLI installation from the test environment."""

    @abstractmethod
    def cleanup_server(self) -> None:
        """Clean up server installation from the test environment."""

    def get_installer_path(self, installer_type: str) -> str:
        """Get the path to the installer script in the test environment.

        Args:
            installer_type: "cli" or "server"

        Returns:
            Path to the installer script
        """
        if installer_type == "cli":
            return "/tmp/install-cli.py"
        return "/tmp/install-server.py"
