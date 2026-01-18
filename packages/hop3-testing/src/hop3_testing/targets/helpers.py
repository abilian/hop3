# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Helper classes for deployment targets.

These are composed into targets rather than inherited, following
the principle of composition over inheritance.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .constants import (
    DEFAULT_HEALTH_CHECK_TIMEOUT,
    HEALTH_CHECK_COMMAND,
    HEALTHY_STATUS_CODES,
)

if TYPE_CHECKING:
    from hop3_testing.diagnostics import DiagnosticCollector


class CommandRunner(Protocol):
    """Protocol for objects that can run commands."""

    def run(self, command: str, *, check: bool = False) -> Any:
        """Run a command and return result with stdout attribute."""
        ...


class ContainerRunner(Protocol):
    """Protocol for Docker container-like objects."""

    def exec_run(self, command: str) -> Any:
        """Execute command in container, return result with output attribute."""
        ...

    def reload(self) -> None:
        """Reload container state."""
        ...

    @property
    def status(self) -> str:
        """Container status."""
        ...


@dataclass(frozen=True)
class HealthChecker:
    """Handles health check logic for deployment targets.

    This class encapsulates the logic for checking if a server is ready,
    including the curl command, status code validation, and retry logic.

    Usage:
        checker = HealthChecker(diagnostics)
        is_ready = checker.wait_for_ready(backend)
        is_ready = checker.check_container(container)
    """

    diagnostics: DiagnosticCollector | None = None
    """Optional diagnostics collector for logging."""

    timeout: int = DEFAULT_HEALTH_CHECK_TIMEOUT
    """Maximum wait time in seconds."""

    poll_interval: int = 2
    """Time between health checks."""

    progress_interval: int = 10
    """How often to print progress (seconds)."""

    def check_status_code(self, output: str) -> bool:
        """Check if output contains a healthy status code.

        Args:
            output: Output from health check command (e.g., "200" or "404")

        Returns:
            True if output indicates server is healthy
        """
        return any(code in output for code in HEALTHY_STATUS_CODES)

    def check_status_code_bytes(self, output: bytes) -> bool:
        """Check if bytes output contains a healthy status code.

        Args:
            output: Bytes output from container exec

        Returns:
            True if output indicates server is healthy
        """
        return any(code.encode() in output for code in HEALTHY_STATUS_CODES)

    def wait_for_ready(
        self,
        runner: CommandRunner,
        *,
        timeout: int | None = None,
        on_timeout: Any | None = None,
    ) -> bool:
        """Wait for server to be ready using a command runner.

        Args:
            runner: Object with run() method (e.g., DeployBackend)
            timeout: Override default timeout (uses self.timeout if not provided)
            on_timeout: Optional callback to run on timeout (for extra diagnostics)

        Returns:
            True if server became ready, False if timeout
        """
        print("Waiting for hop3-server to be ready...")
        start_time = time.time()
        last_status = "unknown"
        max_wait = timeout or self.timeout

        while time.time() - start_time < max_wait:
            try:
                result = runner.run(HEALTH_CHECK_COMMAND, check=False)
                last_status = result.stdout.strip()

                if self.check_status_code(result.stdout):
                    self._log_success(start_time, last_status)
                    print(f"✓ hop3-server is responding (status: {last_status})")
                    return True

                self._log_progress(start_time, last_status)

            except Exception as e:
                self._log_failure(e)

            time.sleep(self.poll_interval)

        # Timeout - run callback if provided
        print(f"  Health check timed out after {max_wait}s. Last status: {last_status}")
        if on_timeout:
            on_timeout()

        return False

    def wait_for_container(
        self,
        container: ContainerRunner,
        timeout: int | None = None,
    ) -> bool:
        """Wait for server to be ready in a Docker container.

        Args:
            container: Docker container object
            timeout: Override default timeout

        Returns:
            True if server became ready, False if timeout
        """
        print("Waiting for hop3-server to be ready...")
        start_time = time.time()
        max_wait = timeout or self.timeout

        while time.time() - start_time < max_wait:
            try:
                container.reload()
                if container.status != "running":
                    return False

                result = container.exec_run(HEALTH_CHECK_COMMAND)
                if self.check_status_code_bytes(result.output):
                    print("✓ hop3-server is responding")
                    return True

            except Exception:
                pass

            time.sleep(self.poll_interval)

        return False

    def is_ready(self, runner: CommandRunner) -> bool:
        """Quick check if server is ready (no waiting).

        Args:
            runner: Object with run() method

        Returns:
            True if server is responding
        """
        try:
            result = runner.run(HEALTH_CHECK_COMMAND, check=False)
            return self.check_status_code(result.stdout)
        except Exception:
            return False

    def is_container_ready(self, container: ContainerRunner) -> bool:
        """Quick check if container's server is ready.

        Args:
            container: Docker container object

        Returns:
            True if server is responding
        """
        try:
            container.reload()
            if container.status != "running":
                return False
            result = container.exec_run(HEALTH_CHECK_COMMAND)
            return self.check_status_code_bytes(result.output)
        except Exception:
            return False

    def _log_success(self, start_time: float, status: str) -> None:
        """Log successful health check."""
        if self.diagnostics:
            self.diagnostics.add_success(
                layer="server",
                operation="health_check",
                message="hop3-server is responding",
                duration=time.time() - start_time,
                details={"status_code": status},
            )

    def _log_progress(self, start_time: float, status: str) -> None:
        """Log progress during wait."""
        elapsed = int(time.time() - start_time)
        if elapsed > 0 and elapsed % self.progress_interval == 0:
            print(f"  ... waiting ({elapsed}s), last status: {status}")

    def _log_failure(self, error: Exception) -> None:
        """Log health check failure."""
        if self.diagnostics:
            self.diagnostics.add_failure(
                layer="server",
                operation="health_check_attempt",
                message=f"Health check failed: {error}",
            )


@dataclass(frozen=True)
class DiagnosticsHelper:
    """Helper for common diagnostics operations.

    Wraps DiagnosticCollector with common save/dump operations
    used across multiple target types.
    """

    diagnostics: DiagnosticCollector
    """The diagnostics collector to wrap."""

    def save_on_error(self) -> Path:
        """Save diagnostics and print to console on error.

        Returns:
            Path to saved log directory
        """
        print(self.diagnostics.dump_to_console())
        log_path = self.diagnostics.save_logs()
        print(f"\nDiagnostic logs saved to: {log_path}")
        return log_path

    def save(self, generate_html: bool = False) -> Path:
        """Save all diagnostic information to files.

        Args:
            generate_html: If True, also generate HTML report

        Returns:
            Path to the log directory
        """
        log_path = self.diagnostics.save_logs()

        if generate_html:
            html_path = self.diagnostics.generate_html_report()
            print(f"HTML report saved to: {html_path}")

        return log_path

    def collect_server_diagnostics(self, runner: CommandRunner) -> None:
        """Collect diagnostic information from server.

        Args:
            runner: Object with run() method to execute commands
        """
        self.diagnostics.set_phase("diagnostics")
        try:
            # Check systemd service
            result = runner.run(
                "systemctl status hop3-server 2>&1 || true",
                check=False,
            )
            self.diagnostics.add_success(
                layer="server",
                operation="systemd_status",
                message="hop3-server systemd status collected",
                stdout=result.stdout,
                stderr=result.stderr,
                details={"type": "diagnostic_info"},
            )

            # Check server logs
            result = runner.run(
                "journalctl -u hop3-server -n 50 --no-pager 2>&1 || true",
                check=False,
            )
            self.diagnostics.add_success(
                layer="server",
                operation="server_logs",
                message="hop3-server journal logs collected",
                stdout=result.stdout,
                details={"type": "diagnostic_info"},
            )

            # Check listening ports
            result = runner.run(
                "ss -tlnp 2>&1 || netstat -tlnp 2>&1 || true",
                check=False,
            )
            self.diagnostics.add_success(
                layer="server",
                operation="listening_ports",
                message="Listening ports collected",
                stdout=result.stdout,
                details={"type": "diagnostic_info"},
            )

        except Exception as e:
            self.diagnostics.add_failure(
                layer="server",
                operation="collect_diagnostics",
                message=f"Failed to collect diagnostics: {e}",
            )


@dataclass
class DockerContainerHelper:
    """Helper for common Docker container operations.

    Consolidates port extraction, SSH key extraction, and container
    lifecycle management that was previously duplicated across
    DockerTarget, DockerDeployTarget, and ReadyTarget.
    """

    container: Any
    """Docker container object."""

    _ssh_key_path: Path | None = field(default=None, init=False)
    """Path to extracted SSH key (internal)."""

    def get_mapped_port(self, container_port: int) -> int | None:
        """Extract host port mapping for a container port.

        Args:
            container_port: Port inside the container (e.g., 22, 80, 8000)

        Returns:
            Host port that maps to the container port, or None if not mapped
        """
        self.container.reload()
        ports = self.container.attrs["NetworkSettings"]["Ports"]
        port_key = f"{container_port}/tcp"
        if port_key not in ports or not ports[port_key]:
            return None
        return int(ports[port_key][0]["HostPort"])

    def extract_ssh_key(self) -> Path:
        """Extract SSH key from container to temp file.

        Returns:
            Path to temp file containing SSH private key
        """
        result = self.container.exec_run("cat /home/hop3/.ssh/id_rsa")
        ssh_key = result.output.decode()

        key_path = Path("/tmp") / f"hop3-key-{self.container.short_id}"
        key_path.write_text(ssh_key)
        key_path.chmod(0o600)
        self._ssh_key_path = key_path
        return key_path

    def stop_and_remove(self) -> None:
        """Safely stop and remove the container."""
        try:
            self.container.reload()
            if self.container.status == "running":
                self.container.stop(timeout=10)
            self.container.remove(force=True)
        except Exception:
            pass  # Container may already be stopped/removed

        # Clean up SSH key file
        if self._ssh_key_path and self._ssh_key_path.exists():
            self._ssh_key_path.unlink()

    def exec_run(self, cmd: str, demux: bool = False) -> Any:
        """Execute a command in the container.

        Args:
            cmd: Command to execute
            demux: If True, separate stdout and stderr

        Returns:
            Execution result from Docker SDK
        """
        return self.container.exec_run(cmd, demux=demux)

    def get_logs(self, stream: bool = False) -> Any:
        """Get container logs.

        Args:
            stream: If True, return streaming iterator

        Returns:
            Logs as bytes or iterator
        """
        return self.container.logs(stream=stream)

    @property
    def status(self) -> str:
        """Get container status (running, exited, etc.)."""
        self.container.reload()
        return self.container.status

    @property
    def container_id(self) -> str:
        """Get container ID."""
        return self.container.id

    @property
    def short_id(self) -> str:
        """Get short container ID."""
        return self.container.short_id

    @property
    def name(self) -> str:
        """Get container name."""
        return self.container.name


def find_project_root() -> Path:
    """Find the project root directory.

    Returns:
        Path to project root (directory containing pyproject.toml and packages/)

    Raises:
        RuntimeError: If project root cannot be found
    """
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "packages").exists():
            return current
        current = current.parent

    msg = "Could not find project root"
    raise RuntimeError(msg)
