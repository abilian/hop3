# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Base class for deployment backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_installer.common import CommandResult

if TYPE_CHECKING:
    from hop3_installer.deployer.config import DeployConfig

# Re-export for backwards compatibility
__all__ = ["CommandResult", "DeployBackend"]


class DeployBackend(ABC):
    """Abstract base class for deployment backends."""

    name: str = "base"

    def __init__(self, config: DeployConfig):
        """Initialize the backend.

        Args:
            config: Deployment configuration
        """
        self.config = config

    @abstractmethod
    def setup(self) -> bool:
        """Set up the deployment target.

        For SSH, this verifies connectivity.
        For Docker, this starts the container.

        Returns:
            True if setup succeeded, False otherwise
        """

    @abstractmethod
    def teardown(self) -> None:
        """Clean up after deployment.

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

    def run_streaming(
        self, command: str, *, quiet: bool = False, log_file: Path | None = None
    ) -> int:
        """Run a command with output handling based on mode.

        Args:
            command: Command to execute
            quiet: If True, capture output to log file instead of terminal
            log_file: File to write output to (required if quiet=True)

        Returns:
            Exit code of the command
        """
        # Default implementation falls back to regular run
        result = self.run(command, check=False)

        if quiet and log_file:
            with Path(log_file).open("a") as f:
                f.write(f"\n=== Command: {command} ===\n")
                if result.stdout:
                    f.write(result.stdout)
                if result.stderr:
                    f.write(f"\n--- stderr ---\n{result.stderr}")
                f.write(f"\n=== Exit code: {result.returncode} ===\n")
        else:
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)

        return result.returncode

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
    def clean(self) -> None:
        """Clean the target before fresh installation."""

    @abstractmethod
    def get_server_url(self) -> str:
        """Get the URL to access the Hop3 server.

        Returns:
            URL string (e.g., http://192.168.1.100:8000)
        """
