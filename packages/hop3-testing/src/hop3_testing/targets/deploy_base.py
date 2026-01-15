# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Base class for deployment targets that use hop3-deploy.

This module provides a shared base class for DockerDeployTarget and RemoteDeployTarget,
using composition for common functionality like diagnostics and health checks.
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hop3_testing.diagnostics import DiagnosticCollector

from .base import DeploymentTarget, TargetInfo
from .helpers import DiagnosticsHelper, HealthChecker, find_project_root

if TYPE_CHECKING:
    from hop3_installer.deployer.backends.base import DeployBackend


class DeployTargetBase(DeploymentTarget):
    """Base class for deployment targets that use hop3-deploy infrastructure.

    This class provides shared functionality for targets that deploy Hop3
    using the hop3-deploy infrastructure (DockerDeployTarget, RemoteDeployTarget).

    Uses composition for:
        - HealthChecker: Health check logic
        - DiagnosticsHelper: Diagnostic save/dump operations

    Subclasses must implement:
        - start(): Initialize and deploy to the target
        - stop(): Cleanup the target
        - _build_target_info(): Create TargetInfo from backend
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.config = config or {}

        # Setup diagnostics with file logging
        log_dir = self.config.get("log_dir")
        self.diagnostics = DiagnosticCollector(
            verbose=self.config.get("verbose", False),
            log_dir=Path(log_dir) if log_dir else None,
        )

        # Compose helpers
        self._diagnostics_helper = DiagnosticsHelper(self.diagnostics)
        self._health_checker = HealthChecker(self.diagnostics)

        # Deployment options
        self.use_local = self.config.get("local", True)
        self.clean_before = self.config.get("clean", False)
        self.branch = self.config.get("branch", "devel")

        # State
        self._deployer_backend: DeployBackend | None = None
        self._started = False

    @abstractmethod
    def start(self) -> TargetInfo:
        """Start the deployment target."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the deployment target."""

    @abstractmethod
    def _build_target_info(self) -> TargetInfo:
        """Build TargetInfo from deployer backend."""

    def _save_diagnostics_on_error(self) -> None:
        """Save diagnostics to files and print to console on error."""
        self._diagnostics_helper.save_on_error()

    def _find_project_root(self) -> Path:
        """Find the project root directory."""
        return find_project_root()

    def _wait_for_ready(self, max_wait: int = 120) -> bool:
        """Wait for hop3-server to be ready.

        Args:
            max_wait: Maximum time to wait in seconds

        Returns:
            True if server is ready
        """
        self._health_checker.timeout = max_wait
        return self._health_checker.wait_for_ready(
            self._deployer_backend,
            on_timeout=lambda: self._diagnostics_helper.collect_server_diagnostics(
                self._deployer_backend
            ),
        )

    def _collect_server_diagnostics(self) -> None:
        """Collect diagnostic information from the server."""
        self._diagnostics_helper.collect_server_diagnostics(self._deployer_backend)

    def save_diagnostics(self, generate_html: bool = False) -> Path:
        """Save all diagnostic information to files.

        Args:
            generate_html: If True, also generate HTML report.

        Returns:
            Path to the log directory.
        """
        return self._diagnostics_helper.save(generate_html)

    def is_ready(self) -> bool:
        """Check if the target is ready."""
        if not self._started or not self._deployer_backend:
            return False
        return self._health_checker.is_ready(self._deployer_backend)

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Execute a command on the target."""
        if not self._deployer_backend:
            msg = "Target not started"
            raise RuntimeError(msg)

        if isinstance(cmd, list):
            cmd = " ".join(cmd)

        result = self._deployer_backend.run(cmd, check=False)
        return result.returncode, result.stdout, result.stderr
