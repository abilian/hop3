# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Helper classes for deployment targets.

These are composed into targets rather than inherited, following
the principle of composition over inheritance.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from hop3_testing.exceptions import ConfigurationError, ServiceStartError
from hop3_testing.util.streaming import run_streaming

from .constants import (
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_HEALTH_CHECK_TIMEOUT,
    E2E_TEST_SECRET_KEY,
    HEALTH_CHECK_COMMAND,
    HEALTHY_STATUS_CODES,
)

if TYPE_CHECKING:
    from collections.abc import Callable

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

    def exec_run(self, cmd: list[str] | str, **kwargs: Any) -> Any:
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
        # Distinct from the diagnostic *bundle* (~/.hop3/test-runs/<run-id>) that
        # the runner prints on a startup failure: this is the raw deploy-phase
        # capture. Two different artifacts — don't label both "saved to".
        print(f"\nDeploy logs saved to: {log_path}")
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

        SECURITY: create the file with restrictive perms *before* writing
        the key. The earlier shape used ``write_text(...)`` (default
        umask, typically 0o644) followed by ``chmod 0o600`` — there's a
        race window during which other local users on the workstation
        could read the SSH private key. ``mkstemp`` creates the file at
        0o600 from the start, and ``os.fchmod`` on the descriptor before
        close pins it.
        """
        result = self.container.exec_run("cat /home/hop3/.ssh/id_rsa")
        ssh_key = result.output.decode()

        fd, tmp_str = tempfile.mkstemp(
            prefix=f"hop3-key-{self.container.short_id}-",
            dir="/tmp",
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(ssh_key)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_str)
            raise

        key_path = Path(tmp_str)
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

    def start_all(self) -> None:
        """Start all services needed for Hop3.

        Raises:
            ServiceStartError: If any service fails to start.
        """
        print("Starting services manually (Docker has no systemd)...")

        try:
            self._setup_ssh()
            self._start_ssh()
            self._start_nginx()
            self._start_postgresql()
            self._start_uwsgi()
            self._start_hop3_server()
            self._verify_hop3_server()
            print("  Services started")

        except ServiceStartError:
            raise
        except Exception as e:
            if self.diagnostics:
                self.diagnostics.add_failure(
                    layer="server",
                    operation="start_services",
                    message=f"Exception starting services: {e}",
                )
            msg = f"Failed to start services: {e}"
            raise ServiceStartError(msg) from e

    def _setup_ssh(self) -> None:
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

    def _start_ssh(self) -> None:
        """Start SSH daemon."""
        print("  Starting SSH daemon...")
        self.backend.run(
            "/usr/sbin/sshd || echo 'sshd may already be running'",
            check=False,
        )
        time.sleep(1)

    def _start_nginx(self) -> None:
        """Start nginx."""
        print("  Starting nginx...")
        self.backend.run(
            "nginx || nginx -g 'daemon off;' &",
            check=False,
        )

    def _start_postgresql(self) -> None:
        """Start PostgreSQL."""
        print("  Starting PostgreSQL...")
        self.backend.run(
            "su - postgres -c 'pg_ctlcluster 16 main start' 2>/dev/null || "
            "service postgresql start 2>/dev/null || true",
            check=False,
        )

    def _start_uwsgi(self) -> None:
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

    def _start_hop3_server(self) -> None:
        """Start hop3-server."""
        print("  Starting hop3-server...")
        self.backend.run(
            "su - hop3 -c '"
            # Auth is real: the server signs/validates with this known test key,
            # and the harness mints tokens with the same key (no HOP3_UNSAFE
            # bypass). This inline start has no /etc/hop3/secret-key file, so the
            # env key is the effective one.
            f'export HOP3_SECRET_KEY="{E2E_TEST_SECRET_KEY}" && '
            'export HOP3_DB_URL="sqlite:////home/hop3/hop3.db" && '
            'export ACME_ENGINE="self-signed" && '
            "nohup /home/hop3/venv/bin/hop3-server serve "
            "> /home/hop3/hop3-server.log 2>&1 &'",
            check=False,
        )
        time.sleep(3)

    def _verify_hop3_server(self) -> None:
        """Verify hop3-server is running.

        Raises:
            ServiceStartError: If hop3-server is not running.
        """
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
            msg = f"hop3-server process not running. Log: {log_result.stdout[:500]}"
            raise ServiceStartError(msg)


def read_server_secret_key(
    backend: CommandRunner,
    diagnostics: DiagnosticCollector | None = None,
) -> str:
    """Read the deployed server's JWT signing key.

    The harness authenticates for real — it mints a token signed with the
    server's own key (``create_test_token(secret_key=...)``) instead of
    disabling authentication with ``HOP3_UNSAFE``. We therefore need the key the
    server actually validates with.

    Mirrors the server's ``get_secret_key`` precedence (ADR 048): the canonical
    ``/etc/hop3/secret-key`` file first, then ``HOP3_SECRET_KEY`` in
    ``/etc/default/hop3``. Reads as the SSH user (root), so the 0600 file is
    readable.

    Raises:
        ConfigurationError: if no key can be read — we fail loud rather than
            fall back to a key the server would reject (which would surface
            later as an opaque "Authentication required").
    """
    print("Reading the server's signing key (for real-auth test tokens)...")

    try:
        result = backend.run(
            "cat /etc/hop3/secret-key 2>/dev/null "
            "|| grep -h '^HOP3_SECRET_KEY=' /etc/default/hop3 2>/dev/null "
            "| head -n1 | cut -d= -f2-",
            check=False,
        )
        key = (result.stdout or "").strip().strip('"').strip("'")
        if not key:
            msg = (
                "Could not read the server's JWT signing key from "
                "/etc/hop3/secret-key or /etc/default/hop3. The harness needs it "
                "to mint tokens the server accepts; aborting rather than using a "
                "key the server would reject."
            )
            if diagnostics:
                diagnostics.add_failure(
                    layer="server",
                    operation="read_secret_key",
                    message=msg,
                    stdout=result.stdout,
                )
            raise ConfigurationError(msg)

        if diagnostics:
            diagnostics.add_success(
                layer="server",
                operation="read_secret_key",
                message="Read server signing key for real-auth test tokens",
            )
        print("  ✓ Server signing key read")
        return key

    except ConfigurationError:
        raise
    except Exception as e:
        if diagnostics:
            diagnostics.add_failure(
                layer="server",
                operation="read_secret_key",
                message=f"Exception reading server signing key: {e}",
            )
        msg = f"Exception reading server signing key: {e}"
        raise ConfigurationError(msg) from e


_LEGACY_SOURCE_FLAG = {"local": "--local", "git": "--git", "pypi": "--pypi"}


def _source_flags(
    source: str, branch: str, version: str | None, *, legacy: bool
) -> list[str]:
    """The install-source flags: --from/--local + --branch (git) / --version (pypi).

    ``legacy`` emits the old --local/--git/--pypi spellings accepted by every
    version's deployer (needed to drive a pre-ADR-052 release's own deployer);
    otherwise the canonical --from.
    """
    flags = [_LEGACY_SOURCE_FLAG[source]] if legacy else ["--from", source]
    if source == "git":
        flags += ["--branch", branch]
    if source == "pypi" and version:
        flags += ["--version", version]
    return flags


def _build_deploy_command(
    *,
    docker: bool,
    host: str | None,
    user: str,
    container_name: str,
    image: str,
    source: str = "local",
    clean: bool,
    branch: str,
    version: str | None = None,
    legacy_flags: bool = False,
    verbose: bool,
    features: list[str] | None = None,
    ssh_key: str | None = None,
    domain: str | None = None,
    acme_email: str | None = None,
) -> list[str]:
    """Build the hop3-deploy-server command (canonical ADR 052 flags).

    ``source`` is the install source ("local" | "git" | "pypi"), emitted as
    ``--from``. For git the branch is passed ALWAYS and explicitly, so the
    deployer installs exactly this ref regardless of its own default branch
    (``main``). This fixes the footgun where an unspecified/default branch on a
    git deploy silently fell back to PyPI (the old ``if branch != "devel"``
    skip, made wrong by the default flip).
    """
    cmd = ["hop3-deploy-server"]

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
        cmd.extend(["--host", host, "--user", user])
        if ssh_key:
            # The deploy's ssh otherwise uses its default identity, which a
            # server-resident runtime user doesn't have -> Permission denied.
            cmd.extend(["--identity", ssh_key])

    cmd.extend(_source_flags(source, branch, version, legacy=legacy_flags))
    if clean:
        cmd.append("--clean")
    if verbose:
        cmd.append("--verbose")
    if features:
        cmd.extend(["--with", ",".join(features)])
    # Admin/ACME setup (cloud path). Emitted only when configured, so the plain
    # run path (domain=None) is unaffected — but when the cloud caller sets a
    # domain, it must reach the deployer or admin/ACME setup silently vanishes.
    if domain:
        cmd.extend(["--admin-domain", domain])
    if acme_email:
        cmd.extend(["--acme-email", acme_email])

    return cmd


def run_hop3_deploy(
    *,
    docker: bool = False,
    host: str | None = None,
    user: str = "root",
    container_name: str = "hop3-test",
    image: str = DEFAULT_DOCKER_IMAGE,
    source: str = "local",
    clean: bool = False,
    branch: str = "main",
    version: str | None = None,
    legacy_flags: bool = False,
    verbose: bool = False,
    features: list[str] | None = None,
    ssh_key: str | None = None,
    domain: str | None = None,
    acme_email: str | None = None,
    command_prefix: list[str] | None = None,
    cwd: Path | str | None = None,
    on_output: Callable[[str], None] | None = None,
    diagnostics: DiagnosticCollector | None = None,
) -> tuple[bool, float]:
    """Run hop3-deploy-server via subprocess.

    This invokes hop3-deploy-server as a CLI tool rather than importing its
    internals, keeping hop3-testing decoupled from hop3-installer.

    Args:
        docker: If True, deploy to Docker container
        host: Remote host (required if not docker)
        user: SSH user for remote deployment
        container_name: Docker container name
        image: Docker base image
        source: Install source ("local" | "git" | "pypi"), emitted as --from
        clean: Clean before deploy (--clean flag)
        branch: Git branch to deploy (only used when source == "git")
        version: Pinned PyPI version, emitted as --version (only when source == "pypi")
        legacy_flags: Emit old-style source flags (--local/--git/--pypi) accepted by
            every version's deployer — for driving an OLD version's own deployer
        verbose: Enable verbose output
        features: Features to install (docker, mysql, redis, nix, etc.)
        domain: Admin domain, emitted as --admin-domain (cloud path)
        acme_email: Let's Encrypt email, emitted as --acme-email (cloud path)
        command_prefix: Prepended to the command (e.g. ["uv", "run"]) so a caller
            deploying from a source checkout can invoke the deployer via uv
        cwd: Working directory for the deploy subprocess (e.g. a cloned repo)
        on_output: Called for each output line (in addition to printing), so a
            caller can capture the deploy transcript (e.g. the cloud path's
            DeploymentResult.log_output)
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
        source=source,
        clean=clean,
        branch=branch,
        version=version,
        legacy_flags=legacy_flags,
        verbose=verbose,
        features=features,
        ssh_key=ssh_key,
        domain=domain,
        acme_email=acme_email,
    )
    if command_prefix:
        cmd = [*command_prefix, *cmd]

    print(f"\nRunning: {' '.join(cmd)}\n")

    if diagnostics:
        diagnostics.set_phase("deploy")

    start_time = time.time()

    # `hop3-deploy --clean --with all` can take 10-20 minutes on a cold
    # docker image (apt install, nix single-user install, extensions).
    # Stream output line-by-line so the user sees progress in real time,
    # while still capturing the full log for the diagnostics failure
    # report. A 4-hour timeout is generous but bounded — the process
    # group gets killed on timeout so no orphaned nix-build / docker.
    def _emit(line: str) -> None:
        print(line, flush=True)
        if on_output is not None:
            on_output(line)

    try:
        result = run_streaming(
            cmd,
            on_output=_emit,
            timeout=4 * 3600,
            cwd=cwd,
        )
    except FileNotFoundError:
        duration = time.time() - start_time
        _log_deploy_not_found(diagnostics, duration)
        return False, duration

    duration = time.time() - start_time

    if result.timed_out:
        _log_deploy_timeout(diagnostics, duration, result)
        return False, duration

    if result.returncode != 0:
        _log_deploy_failure(diagnostics, duration, result)
        return False, duration

    _log_deploy_success(diagnostics, duration)
    return True, duration


def _log_deploy_failure(
    diagnostics: DiagnosticCollector | None,
    duration: float,
    result,
) -> None:
    """Log deployment failure.

    Output was streamed to the console as it arrived; no need to
    re-print it here. The captured transcript still goes to the
    diagnostics report so HTML/JSON reports stay complete.
    """
    if diagnostics:
        diagnostics.add_failure(
            layer="deployer",
            operation="deploy",
            message=f"hop3-deploy-server failed (exit {result.returncode})",
            duration=duration,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    print(f"\nDeploy failed after {duration:.0f}s (exit {result.returncode}).")


def _log_deploy_timeout(
    diagnostics: DiagnosticCollector | None,
    duration: float,
    result,
) -> None:
    """Log deployment timeout — subprocess group has already been killed."""
    if diagnostics:
        diagnostics.add_failure(
            layer="deployer",
            operation="deploy",
            message=f"hop3-deploy-server timed out after {duration:.0f}s",
            duration=duration,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    print(f"\nDeploy timed out after {duration:.0f}s (killed process tree).")


def _log_deploy_success(
    diagnostics: DiagnosticCollector | None,
    duration: float,
) -> None:
    """Log deployment success."""
    if diagnostics:
        diagnostics.add_success(
            layer="deployer",
            operation="deploy",
            message=f"hop3-deploy-server completed in {duration:.1f}s",
            duration=duration,
        )


def _log_deploy_not_found(
    diagnostics: DiagnosticCollector | None,
    duration: float,
) -> None:
    """Log hop3-deploy-server not found error."""
    if diagnostics:
        diagnostics.add_failure(
            layer="deployer",
            operation="deploy",
            message="hop3-deploy-server not found - is hop3-installer installed?",
            duration=duration,
        )
    print("Error: hop3-deploy-server command not found")
