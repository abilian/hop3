# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Helper classes for deployment targets.

These are composed into targets rather than inherited, following
the principle of composition over inheritance.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .constants import (
    DEFAULT_HEALTH_CHECK_TIMEOUT,
    E2E_TEST_SECRET_KEY,
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


@dataclass
class CommandResult:
    """Result of a command execution, compatible with CommandRunner protocol."""

    stdout: str
    stderr: str
    returncode: int

    @property
    def success(self) -> bool:
        """Check if command succeeded."""
        return self.returncode == 0


@dataclass
class DockerCommandRunner:
    """Adapter that makes a Docker container conform to CommandRunner protocol.

    This allows using Docker containers with helpers that expect CommandRunner,
    without depending on hop3-installer's DockerDeployBackend.
    """

    container: Any
    """Docker container object."""

    def run(self, command: str, *, check: bool = False) -> CommandResult:
        """Run a command in the container.

        Args:
            command: Shell command to execute
            check: If True, raise on non-zero exit code

        Returns:
            CommandResult with stdout, stderr, returncode
        """
        result = self.container.exec_run(
            ["bash", "-c", command],
            demux=True,
        )
        stdout = result.output[0].decode() if result.output[0] else ""
        stderr = result.output[1].decode() if result.output[1] else ""

        cmd_result = CommandResult(
            stdout=stdout,
            stderr=stderr,
            returncode=result.exit_code,
        )

        if check and result.exit_code != 0:
            msg = f"Command failed with exit code {result.exit_code}: {stderr}"
            raise RuntimeError(msg)

        return cmd_result


@dataclass
class SSHCommandRunner:
    """Adapter that makes a paramiko SSH client conform to CommandRunner protocol.

    This allows using SSH connections with helpers that expect CommandRunner,
    without depending on hop3-installer's SSHDeployBackend.
    """

    ssh_client: Any
    """paramiko.SSHClient instance."""

    def run(self, command: str, *, check: bool = False) -> CommandResult:
        """Run a command via SSH.

        Args:
            command: Shell command to execute
            check: If True, raise on non-zero exit code

        Returns:
            CommandResult with stdout, stderr, returncode
        """
        _stdin, stdout, stderr = self.ssh_client.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        stdout_text = stdout.read().decode()
        stderr_text = stderr.read().decode()

        cmd_result = CommandResult(
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=exit_code,
        )

        if check and exit_code != 0:
            msg = f"Command failed with exit code {exit_code}: {stderr_text}"
            raise RuntimeError(msg)

        return cmd_result


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


@dataclass
class DockerServiceManager:
    """Manages service startup in Docker containers without systemd.

    Docker containers don't have systemd, so we need to start services manually.
    This class encapsulates all the shell commands needed to start the Hop3 stack.
    """

    backend: CommandRunner
    """Backend to run commands on (e.g., DockerDeployBackend)."""

    diagnostics: DiagnosticCollector | None = None
    """Optional diagnostics collector for logging."""

    def start_all(self) -> bool:
        """Start all services needed for Hop3.

        Returns:
            True if all services started successfully
        """
        print("Starting services manually (Docker has no systemd)...")

        try:
            if not self._setup_ssh():
                return False
            if not self._start_ssh():
                return False
            if not self._start_nginx():
                return False
            if not self._start_postgresql():
                return False
            if not self._start_uwsgi():
                return False
            if not self._start_hop3_server():
                return False
            if not self._verify_hop3_server():
                return False

            print("  Services started")
            return True

        except Exception as e:
            if self.diagnostics:
                self.diagnostics.add_failure(
                    layer="server",
                    operation="start_services",
                    message=f"Exception starting services: {e}",
                )
            return False

    def _setup_ssh(self) -> bool:
        """Setup SSH server and keys."""
        print("  Setting up SSH server...")
        self.backend.run(
            """
            if ! command -v sshd &> /dev/null; then
                apt-get update -qq && apt-get install -y -qq openssh-server
            fi && \
            mkdir -p /home/hop3/.ssh && \
            if [ ! -f /home/hop3/.ssh/id_rsa ]; then
                ssh-keygen -t rsa -b 2048 -f /home/hop3/.ssh/id_rsa -N ""
            fi && \
            cat /home/hop3/.ssh/id_rsa.pub >> /home/hop3/.ssh/authorized_keys && \
            sort -u /home/hop3/.ssh/authorized_keys -o /home/hop3/.ssh/authorized_keys && \
            chmod 700 /home/hop3/.ssh && \
            chmod 600 /home/hop3/.ssh/authorized_keys /home/hop3/.ssh/id_rsa && \
            chmod 644 /home/hop3/.ssh/id_rsa.pub && \
            chown -R hop3:hop3 /home/hop3/.ssh && \
            mkdir -p /var/run/sshd
            """,
            check=False,
        )
        return True

    def _start_ssh(self) -> bool:
        """Start SSH daemon."""
        print("  Starting SSH daemon...")
        self.backend.run(
            "/usr/sbin/sshd || echo 'sshd may already be running'",
            check=False,
        )
        time.sleep(1)
        return True

    def _start_nginx(self) -> bool:
        """Start nginx."""
        print("  Starting nginx...")
        self.backend.run(
            "nginx || nginx -g 'daemon off;' &",
            check=False,
        )
        return True

    def _start_postgresql(self) -> bool:
        """Start PostgreSQL."""
        print("  Starting PostgreSQL...")
        self.backend.run(
            "su - postgres -c 'pg_ctlcluster 16 main start' 2>/dev/null || "
            "service postgresql start 2>/dev/null || true",
            check=False,
        )
        return True

    def _start_uwsgi(self) -> bool:
        """Start uwsgi emperor."""
        print("  Starting uwsgi emperor...")
        self.backend.run(
            "mkdir -p /var/log/uwsgi && chown -R hop3:hop3 /var/log/uwsgi && "
            "mkdir -p /tmp && chmod 1777 /tmp",
            check=False,
        )
        self.backend.run(
            "su - hop3 -c '"
            "nohup /home/hop3/venv/bin/uwsgi --emperor /home/hop3/uwsgi-enabled "
            "--stats /tmp/hop3-uwsgi-stats.sock "
            "> /var/log/uwsgi/emperor.log 2>&1 &'",
            check=False,
        )
        time.sleep(2)
        return True

    def _start_hop3_server(self) -> bool:
        """Start hop3-server."""
        print("  Starting hop3-server...")
        self.backend.run(
            "su - hop3 -c '"
            f'export HOP3_SECRET_KEY="{E2E_TEST_SECRET_KEY}" && '
            'export HOP3_UNSAFE="true" && '
            'export HOP3_DB_URL="sqlite:////home/hop3/hop3.db" && '
            'export ACME_ENGINE="self-signed" && '
            "nohup /home/hop3/venv/bin/hop3-server serve "
            "> /home/hop3/hop3-server.log 2>&1 &'",
            check=False,
        )
        time.sleep(3)
        return True

    def _verify_hop3_server(self) -> bool:
        """Verify hop3-server is running."""
        result = self.backend.run(
            "pgrep -f 'hop3-server serve' || echo 'NOT_RUNNING'",
            check=False,
        )
        if "NOT_RUNNING" in result.stdout:
            log_result = self.backend.run(
                "tail -50 /home/hop3/hop3-server.log 2>/dev/null || echo 'No log'",
                check=False,
            )
            if self.diagnostics:
                self.diagnostics.add_failure(
                    layer="server",
                    operation="verify_hop3_server",
                    message="hop3-server process not running",
                    stdout=log_result.stdout,
                )
            return False
        return True


def configure_server_test_mode(
    backend: CommandRunner,
    diagnostics: DiagnosticCollector | None = None,
) -> bool:
    """Configure a remote server for test mode (disable authentication).

    This sets HOP3_UNSAFE=true in the systemd service and restarts it.
    WARNING: This should only be used for testing purposes.

    Args:
        backend: Backend to run commands on (e.g., SSHDeployBackend)
        diagnostics: Optional diagnostics collector for logging

    Returns:
        True if configuration was successful
    """
    print("Configuring server for test mode (HOP3_UNSAFE=true)...")

    try:
        # Create systemd override directory
        result = backend.run(
            "mkdir -p /etc/systemd/system/hop3-server.service.d",
            check=False,
        )
        if not result.success:
            if diagnostics:
                diagnostics.add_failure(
                    layer="server",
                    operation="create_override_dir",
                    message=f"Failed to create override directory: {result.stderr}",
                )
            return False

        # Create override file with HOP3_UNSAFE=true
        override_content = """[Service]
Environment="HOP3_UNSAFE=true"
"""
        result = backend.run(
            f"cat > /etc/systemd/system/hop3-server.service.d/test-mode.conf << 'EOF'\n{override_content}EOF",
            check=False,
        )
        if not result.success:
            if diagnostics:
                diagnostics.add_failure(
                    layer="server",
                    operation="create_override_file",
                    message=f"Failed to create override file: {result.stderr}",
                )
            return False

        # Reload systemd and restart hop3-server
        result = backend.run(
            "systemctl daemon-reload && systemctl restart hop3-server",
            check=False,
        )
        if not result.success:
            if diagnostics:
                diagnostics.add_failure(
                    layer="server",
                    operation="restart_service",
                    message=f"Failed to restart service: {result.stderr}",
                )
            return False

        # Wait a moment for service to start
        time.sleep(3)

        if diagnostics:
            diagnostics.add_success(
                layer="server",
                operation="configure_test_mode",
                message="Server configured for test mode (HOP3_UNSAFE=true)",
            )
        print("  ✓ Test mode configured")
        return True

    except Exception as e:
        if diagnostics:
            diagnostics.add_failure(
                layer="server",
                operation="configure_test_mode",
                message=f"Exception configuring test mode: {e}",
            )
        return False


def _build_deploy_command(
    *,
    docker: bool,
    host: str | None,
    user: str,
    container_name: str,
    image: str,
    use_local: bool,
    clean: bool,
    branch: str,
    verbose: bool,
) -> list[str]:
    """Build hop3-deploy command arguments."""
    cmd = ["hop3-deploy"]

    if docker:
        cmd.extend([
            "--docker",
            "--docker-container",
            container_name,
            "--docker-image",
            image,
        ])
    else:
        if not host:
            msg = "host is required for SSH deployment"
            raise ValueError(msg)
        cmd.extend(["--host", host, "--ssh-user", user])

    if use_local:
        cmd.append("--local")
    if clean:
        cmd.append("--clean")
    if branch != "devel":
        cmd.extend(["--branch", branch])
    if verbose:
        cmd.append("--verbose")

    return cmd


def run_hop3_deploy(
    *,
    docker: bool = False,
    host: str | None = None,
    user: str = "root",
    container_name: str = "hop3-test",
    image: str = "debian:bookworm",
    use_local: bool = True,
    clean: bool = False,
    branch: str = "devel",
    verbose: bool = False,
    diagnostics: DiagnosticCollector | None = None,
) -> tuple[bool, float]:
    """Run hop3-deploy via subprocess.

    This invokes hop3-deploy as a CLI tool rather than importing its internals,
    maintaining proper separation between hop3-testing and hop3-installer.

    Args:
        docker: If True, deploy to Docker container
        host: Remote host (required if not docker)
        user: SSH user for remote deployment
        container_name: Docker container name
        image: Docker base image
        use_local: Use local code (--local flag)
        clean: Clean before deploy (--clean flag)
        branch: Git branch to deploy
        verbose: Enable verbose output
        diagnostics: Optional diagnostics collector

    Returns:
        Tuple of (success, duration_seconds)
    """
    cmd = _build_deploy_command(
        docker=docker,
        host=host,
        user=user,
        container_name=container_name,
        image=image,
        use_local=use_local,
        clean=clean,
        branch=branch,
        verbose=verbose,
    )

    print(f"\nRunning: {' '.join(cmd)}\n")

    if diagnostics:
        diagnostics.set_phase("deploy")

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=not verbose,
            text=True,
            check=False,
        )
        duration = time.time() - start_time

        if result.returncode != 0:
            _log_deploy_failure(diagnostics, duration, result, verbose)
            return False, duration

        _log_deploy_success(diagnostics, duration)
        return True, duration

    except FileNotFoundError:
        duration = time.time() - start_time
        _log_deploy_not_found(diagnostics, duration)
        return False, duration


def _log_deploy_failure(
    diagnostics: DiagnosticCollector | None,
    duration: float,
    result: subprocess.CompletedProcess,
    verbose: bool,
) -> None:
    """Log deployment failure."""
    if diagnostics:
        diagnostics.add_failure(
            layer="deployer",
            operation="deploy",
            message="hop3-deploy failed",
            duration=duration,
            stdout=result.stdout if not verbose else "",
            stderr=result.stderr if not verbose else "",
        )
    if not verbose and result.stderr:
        print(f"Deploy failed:\n{result.stderr}")


def _log_deploy_success(
    diagnostics: DiagnosticCollector | None,
    duration: float,
) -> None:
    """Log deployment success."""
    if diagnostics:
        diagnostics.add_success(
            layer="deployer",
            operation="deploy",
            message=f"hop3-deploy completed in {duration:.1f}s",
            duration=duration,
        )


def _log_deploy_not_found(
    diagnostics: DiagnosticCollector | None,
    duration: float,
) -> None:
    """Log hop3-deploy not found error."""
    if diagnostics:
        diagnostics.add_failure(
            layer="deployer",
            operation="deploy",
            message="hop3-deploy not found - is hop3-installer installed?",
            duration=duration,
        )
    print("Error: hop3-deploy command not found")
