# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Base class for demo execution backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    """Result of a command execution."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def success(self) -> bool:
        return self.returncode == 0


class DemoBackend(ABC):
    """Abstract base class for demo execution backends.

    This provides a unified interface for running demos against either:
    - SSH: Remote server accessed via SSH
    - Docker: Local container for testing
    """

    name: str = "base"

    @abstractmethod
    def setup(self) -> bool:
        """Set up the demo target.

        For SSH, this verifies connectivity.
        For Docker, this starts the container.

        Returns:
            True if setup succeeded, False otherwise
        """

    @abstractmethod
    def teardown(self) -> None:
        """Clean up after demo execution.

        For SSH, this is a no-op.
        For Docker, this optionally stops the container.
        """

    @abstractmethod
    def run(self, command: str, *, check: bool = True) -> CommandResult:
        """Run a command on the target.

        Args:
            command: Command to execute
            check: Whether to raise on non-zero exit

        Returns:
            CommandResult with returncode, stdout, stderr
        """

    @abstractmethod
    def run_streaming(self, command: str) -> int:
        """Run a command with output streamed to terminal.

        Args:
            command: Command to execute

        Returns:
            Exit code of the command
        """

    @abstractmethod
    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """Upload a file to the target.

        Args:
            local_path: Local file path
            remote_path: Remote destination path

        Returns:
            True if upload succeeded
        """

    @abstractmethod
    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """Upload a directory to the target.

        Args:
            local_path: Local directory path
            remote_path: Remote destination path

        Returns:
            True if upload succeeded
        """

    @abstractmethod
    def is_hop3_installed(self) -> bool:
        """Check if Hop3 is installed on the target.

        Returns:
            True if Hop3 is installed
        """

    @abstractmethod
    def get_server_ip(self) -> str:
        """Get the IP address or hostname of the target.

        Returns:
            IP address or hostname string
        """

    @abstractmethod
    def get_server_url(self) -> str:
        """Get the URL to access the Hop3 server.

        Returns:
            URL string (e.g., http://192.168.1.100:8000)
        """

    @abstractmethod
    def clean(self) -> None:
        """Clean the target before fresh installation."""

    def check_connectivity(self) -> bool:
        """Check if the target is reachable.

        Returns:
            True if target responds to commands
        """
        try:
            result = self.run("echo ok", check=False)
            return result.success and "ok" in result.stdout
        except Exception:
            return False
