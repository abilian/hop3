# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Base class for deployment targets."""

from __future__ import annotations

import os
import subprocess
import tarfile
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx
from typing_extensions import Self

from .constants import E2E_TEST_SECRET_KEY

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class CommandResult:
    """Result of a command execution."""

    success: bool
    stdout: str
    stderr: str
    returncode: int
    duration: float = 0.0


@dataclass
class DeployResult:
    """Result of deploying an application."""

    success: bool
    app_name: str
    app_url: str | None = None
    logs: str = ""
    duration: float = 0.0
    error: str | None = None


@dataclass
class HttpResponse:
    """HTTP response from target."""

    status: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)
    duration: float = 0.0


@dataclass
class TargetCapabilities:
    """What a target can do.

    This describes the capabilities of a deployment target, which
    determines what tests can run on it.
    """

    os: str = "unknown"
    """Operating system (e.g., "debian-12", "ubuntu-24.04")."""

    arch: str = "amd64"
    """CPU architecture."""

    has_systemd: bool = False
    """Whether systemd is available (vs supervisor)."""

    has_docker: bool = False
    """Whether Docker is available (for nested Docker tests)."""

    available_services: list[str] = field(default_factory=list)
    """Available services (e.g., ["postgresql", "redis"])."""

    network_mode: Literal["isolated", "internet"] = "isolated"
    """Network access mode."""

    dns_mode: Literal["none", "static", "wildcard"] = "none"
    """DNS configuration mode."""


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
    capabilities: TargetCapabilities | None = None


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

    def run_command(self, *args: str, timeout: int = 300) -> CommandResult:
        """Run a hop3 command on the target.

        Args:
            *args: Command and arguments (e.g., "backup:create", "my-app")
            timeout: Command timeout in seconds

        Returns:
            CommandResult with success status and output
        """
        target_info = self.info
        start_time = time.time()

        env = os.environ.copy()
        env["HOP3_API_URL"] = f"ssh://{target_info.ssh_host}:{target_info.ssh_port}"
        env["HOP3_SSH_KEY"] = target_info.ssh_key or ""
        env["HOP3_SECRET_KEY"] = E2E_TEST_SECRET_KEY

        # Always add -y flag to skip confirmations in E2E tests
        cmd_args = ["hop3", *args, "-y"]

        result = subprocess.run(
            cmd_args,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )

        return CommandResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            duration=time.time() - start_time,
        )

    def capabilities(self) -> TargetCapabilities:
        """Get target capabilities.

        Override in subclasses to provide accurate capabilities.

        Returns:
            TargetCapabilities describing what this target supports
        """
        return TargetCapabilities()

    def deploy_app(
        self,
        app_path: Path,
        app_name: str,
        env_vars: dict[str, str] | None = None,
        timeout: int = 300,
    ) -> DeployResult:
        """Deploy an application to the target.

        This is a high-level method that creates a tarball and deploys via hop3.

        Args:
            app_path: Path to the application directory
            app_name: Name for the deployed app
            env_vars: Environment variables to set
            timeout: Deployment timeout in seconds

        Returns:
            DeployResult with deployment status
        """
        start_time = time.time()

        try:
            # Create tarball
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
                tarball_path = Path(f.name)

            with tarfile.open(tarball_path, "w:gz") as tar:
                tar.add(app_path, arcname=".")

            # Set environment variables if provided
            if env_vars:
                # TODO: Implement env var upload via hop3 CLI
                pass

            # Deploy via hop3 CLI
            # Read tarball and pipe to hop3 deploy
            result = self.run_command("deploy", app_name, timeout=timeout)

            duration = time.time() - start_time

            if not result.success:
                return DeployResult(
                    success=False,
                    app_name=app_name,
                    logs=result.stdout + result.stderr,
                    duration=duration,
                    error=f"Deploy failed: {result.stderr}",
                )

            # Wait for app to be ready
            app_url = self.get_app_url(app_name)

            return DeployResult(
                success=True,
                app_name=app_name,
                app_url=app_url,
                logs=result.stdout,
                duration=duration,
            )

        except Exception as e:
            return DeployResult(
                success=False,
                app_name=app_name,
                duration=time.time() - start_time,
                error=str(e),
            )
        finally:
            # Cleanup tarball
            if tarball_path.exists():
                tarball_path.unlink()

    def destroy_app(self, app_name: str) -> bool:
        """Destroy a deployed application.

        Args:
            app_name: Name of the app to destroy

        Returns:
            True if successful, False otherwise
        """
        result = self.run_command("destroy", app_name)
        return result.success

    def get_app_url(self, app_name: str) -> str:
        """Get the URL for an application.

        Args:
            app_name: Name of the application

        Returns:
            URL to access the application
        """
        # Default: use http_base from target info
        return f"{self.info.http_base}/{app_name}"

    def http_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: int = 30,
    ) -> HttpResponse:
        """Make an HTTP request to the target.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            headers: Optional headers
            body: Optional request body
            timeout: Request timeout in seconds

        Returns:
            HttpResponse with status, body, and headers
        """
        start_time = time.time()

        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                content=body,
                timeout=timeout,
                follow_redirects=True,
            )

            return HttpResponse(
                status=response.status_code,
                body=response.text,
                headers=dict(response.headers),
                duration=time.time() - start_time,
            )
        except httpx.TimeoutException:
            return HttpResponse(
                status=0,
                body="",
                headers={"error": "timeout"},
                duration=time.time() - start_time,
            )
        except Exception as e:
            return HttpResponse(
                status=0,
                body="",
                headers={"error": str(e)},
                duration=time.time() - start_time,
            )

    def wait_for_app(
        self,
        app_name: str,
        timeout: int = 60,
        poll_interval: int = 2,
    ) -> bool:
        """Wait for an application to be running.

        Args:
            app_name: Name of the application
            timeout: Maximum wait time in seconds
            poll_interval: Time between status checks

        Returns:
            True if app is running, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            result = self.run_command("app:status", app_name)
            if result.success and "RUNNING" in result.stdout.upper():
                return True
            time.sleep(poll_interval)

        return False

    def reset(self) -> None:
        """Reset target to clean state.

        Destroys all deployed apps but keeps the target running.
        Override for more specific cleanup.
        """
        # Get list of apps and destroy each
        result = self.run_command("apps")
        if result.success:
            # Parse app names from output (format varies)
            for line in result.stdout.strip().split("\n"):
                if line and not line.startswith("-") and not line.startswith("Name"):
                    # Try to extract app name (first word)
                    parts = line.split()
                    if parts:
                        app_name = parts[0]
                        self.destroy_app(app_name)

    def __enter__(self) -> Self:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()
