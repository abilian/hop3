# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Base class for deployment targets."""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from typing_extensions import Self

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class CommandResult:
    """Result of a command execution."""

    success: bool
    stdout: str
    stderr: str
    returncode: int


@dataclass
class TargetInfo:
    """Information about a deployment target."""

    ssh_host: str
    ssh_port: int
    ssh_key: str | None = None
    ssh_password: str | None = None
    http_base: str = ""
    api_url: str = ""
    metadata: dict[str, Any] | None = None


class DeploymentTarget(ABC):
    """Abstract base class for deployment targets.

    A deployment target represents a Hop3 server where applications can be
    deployed and tested. This could be a Docker container, a VM, or a remote server.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize the deployment target.

        Args:
            config: Configuration dictionary for the target
        """
        self.config = config or {}
        self._info: TargetInfo | None = None

    @abstractmethod
    def start(self) -> TargetInfo:
        """Start the deployment target.

        Returns:
            TargetInfo with connection details
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop and cleanup the deployment target."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if the target is ready to accept deployments.

        Returns:
            True if the target is ready, False otherwise
        """

    @property
    def info(self) -> TargetInfo:
        """Get target information.

        Returns:
            TargetInfo with connection details

        Raises:
            RuntimeError: If target hasn't been started yet
        """
        if self._info is None:
            msg = "Target not started yet. Call start() first."
            raise RuntimeError(msg)
        return self._info

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Execute a command on the target.

        Args:
            cmd: Command to execute (string or list)

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        msg = "exec_run not implemented for this target"
        raise NotImplementedError(msg)

    def get_logs(self) -> Iterator[str]:
        """Get logs from the target.

        Yields:
            Log lines
        """
        msg = "get_logs not implemented for this target"
        raise NotImplementedError(msg)

    def run_command(self, *args: str) -> CommandResult:
        """Run a hop3 command on the target.

        Args:
            *args: Command and arguments (e.g., "backup:create", "my-app")

        Returns:
            CommandResult with success status and output
        """
        target_info = self.info

        env = os.environ.copy()
        env["HOP3_API_URL"] = f"ssh://{target_info.ssh_host}:{target_info.ssh_port}"
        env["HOP3_SSH_KEY"] = target_info.ssh_key or ""
        env["HOP3_SECRET_KEY"] = "e2e-test-secret-key-do-not-use-in-production"

        # Always add -y flag to skip confirmations in E2E tests
        cmd_args = ["hop3", *args, "-y"]

        result = subprocess.run(
            cmd_args,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        return CommandResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    def __enter__(self) -> Self:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()
