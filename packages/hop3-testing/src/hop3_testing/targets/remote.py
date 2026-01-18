# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Consolidated remote deployment target.

This module provides a single RemoteTarget class that handles all SSH-based
testing scenarios:
1. Connect to existing server (no deployment)
2. Deploy Hop3 via hop3-deploy then connect (with deployment config)

The behavior is determined by whether a DeploymentConfig is provided.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import paramiko

from hop3_testing.diagnostics import DiagnosticCollector

from .base import DeploymentTarget, TargetInfo
from .config import DeploymentConfig, RemoteConfig
from .constants import (
    DEFAULT_HEALTH_CHECK_TIMEOUT,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_ROOT_USER,
    HEALTH_CHECK_COMMAND,
    HEALTHY_STATUS_CODES,
)
from .helpers import (
    DiagnosticsHelper,
    HealthChecker,
    configure_server_test_mode,
    find_project_root,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hop3_installer.deployer.backends.base import DeployBackend


class RemoteTarget(DeploymentTarget):
    """SSH-based target for all remote testing scenarios.

    This class consolidates RemoteTarget (connect-only) and RemoteDeployTarget
    (deploy then connect) into a single class with optional deployment.

    Usage Modes:

    1. **Connect-only mode** (no deployment config):
       Connects to an existing Hop3 server via SSH.
       ```python
       target = RemoteTarget(RemoteConfig(host="server.example.com"))
       ```

    2. **Deploy mode** (with deployment config):
       Deploys Hop3 via hop3-deploy, then connects.
       ```python
       target = RemoteTarget(
           RemoteConfig(host="server.example.com"),
           deployment=DeploymentConfig(source="local", clean=True)
       )
       ```

    Examples:
        # App testing: connect to existing Hop3 server
        target = RemoteTarget(RemoteConfig(host="server.example.com"))

        # App testing with SSH key
        target = RemoteTarget(RemoteConfig(
            host="server.example.com",
            ssh_key="~/.ssh/id_rsa"
        ))

        # System testing: deploy Hop3 first
        target = RemoteTarget(
            RemoteConfig(host="server.example.com"),
            deployment=DeploymentConfig(source="local", clean=True)
        )

        # Context manager usage
        with RemoteTarget(RemoteConfig(host="...")) as target:
            result = target.exec_run("hop3 apps")
    """

    def __init__(
        self,
        config: RemoteConfig,
        deployment: DeploymentConfig | None = None,
    ):
        """Initialize remote target.

        Args:
            config: Remote server configuration (host, port, user, etc.)
            deployment: Optional deployment configuration. If provided, Hop3
                       will be deployed before connecting.
        """
        super().__init__()
        self.remote_config = config
        self.deployment = deployment

        # Ensure log directory exists
        self.remote_config.log_dir.mkdir(parents=True, exist_ok=True)

        # Setup diagnostics
        self.diagnostics = DiagnosticCollector(
            verbose=deployment.verbose if deployment else False,
            log_dir=self.remote_config.log_dir,
        )

        # Compose helpers
        self._diagnostics_helper = DiagnosticsHelper(self.diagnostics)
        self._health_checker = HealthChecker(
            self.diagnostics,
            timeout=DEFAULT_HEALTH_CHECK_TIMEOUT,
        )

        # State
        self._ssh_client: paramiko.SSHClient | None = None
        self._deployer_backend: DeployBackend | None = None
        self._started = False

    def start(self) -> TargetInfo:
        """Start the remote target.

        If deployment config is provided, deploys Hop3 first.
        Otherwise, just connects to the existing server.

        Returns:
            TargetInfo with connection details

        Raises:
            RuntimeError: If connection or deployment fails
        """
        if self.deployment:
            return self._deploy_and_connect()
        return self._connect_only()

    def _connect_only(self) -> TargetInfo:
        """Connect to an existing Hop3 server via SSH.

        Returns:
            TargetInfo with connection details
        """
        config = self.remote_config
        print("\n" + "=" * 60)
        print(f"Connecting to remote Hop3 server at {config.host}:{config.port}...")
        print("=" * 60)

        # Create and configure SSH client
        self._ssh_client = paramiko.SSHClient()
        self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Build connection parameters
        connect_kwargs = self._build_ssh_connect_kwargs()

        try:
            self._ssh_client.connect(**connect_kwargs)
            print(f"✓ Connected to {config.user}@{config.host}:{config.port}")
        except Exception as e:
            msg = f"Failed to connect to remote server: {e}"
            raise RuntimeError(msg) from e

        # Check if server is ready
        if not self._check_server_ready_ssh():
            msg = "Remote server is not ready (hop3-server not responding)"
            raise RuntimeError(msg)

        # Build target info
        self._info = self._build_target_info()
        self._started = True

        print("\nRemote target ready:")
        print(f"  SSH: ssh -p {config.port} {config.user}@{config.host}")
        print(f"  HTTP: {self._info.http_base}")
        print(f"  API: {self._info.api_url}")
        print("=" * 60 + "\n")

        return self._info

    def _deploy_and_connect(self) -> TargetInfo:
        """Deploy Hop3 via hop3-deploy, then connect.

        Returns:
            TargetInfo with connection details
        """
        # Lazy imports to avoid circular dependencies
        from hop3_installer.deployer.backends.ssh import (  # noqa: PLC0415
            SSHDeployBackend,
        )
        from hop3_installer.deployer.config import DeployConfig  # noqa: PLC0415
        from hop3_installer.deployer.deploy import Deployer  # noqa: PLC0415

        config = self.remote_config
        deployment = self.deployment
        assert deployment is not None  # Type narrowing

        start_time = time.time()

        # Initialize diagnostic context
        self.diagnostics.set_context(
            test_name=f"system-{config.host}",
            config="remote-deploy",
        )
        self.diagnostics.set_phase("setup")

        print("\n" + "=" * 70)
        print(f"Deploying Hop3 to remote server: {config.user}@{config.host}")
        print("=" * 70)

        try:
            # Find project root
            project_root = find_project_root()

            self.diagnostics.add_success(
                layer="testing",
                operation="find_project_root",
                message=f"Found project root at {project_root}",
            )

            # Create deployer config
            deploy_config = DeployConfig(
                host=config.host,
                ssh_user=config.user,
                ssh_port=config.port,
                use_local_code=deployment.source == "local",
                clean_before=deployment.clean,
                branch=deployment.branch,
                project_root=project_root,
                verbose=deployment.verbose,
                quiet=False,
            )

            self.diagnostics.add_success(
                layer="deployer",
                operation="create_config",
                message="Created deployment configuration",
                details={
                    "host": config.host,
                    "user": config.user,
                    "source": deployment.source,
                    "clean": deployment.clean,
                    "branch": deployment.branch,
                },
            )

            # Print equivalent CLI command
            cli_cmd = self._build_cli_command()
            print(f"\nEquivalent command: {cli_cmd}\n")

            # Create backend and deployer
            self._deployer_backend = SSHDeployBackend(deploy_config)
            deployer = Deployer(deploy_config, self._deployer_backend)

            # Run deployment
            self.diagnostics.set_phase("deploy")
            print("\nRunning hop3-deploy...")
            deploy_start = time.time()
            success = deployer.deploy()
            deploy_duration = time.time() - deploy_start

            if not success:
                self.diagnostics.add_failure(
                    layer="deployer",
                    operation="deploy",
                    message="hop3-deploy failed",
                    duration=deploy_duration,
                )
                self._save_diagnostics_on_error()
                msg = "hop3-deploy failed - see diagnostics above"
                raise RuntimeError(msg)

            self.diagnostics.add_success(
                layer="deployer",
                operation="deploy",
                message=f"hop3-deploy completed in {deploy_duration:.1f}s",
                duration=deploy_duration,
            )

            # Configure server for test mode
            self.diagnostics.set_phase("configure_test_mode")
            if not configure_server_test_mode(self._deployer_backend, self.diagnostics):
                self.diagnostics.add_failure(
                    layer="server",
                    operation="configure_test_mode",
                    message="Failed to configure test mode",
                )
                self._save_diagnostics_on_error()
                msg = "Failed to configure test mode - see diagnostics above"
                raise RuntimeError(msg)

            # Wait for server to be ready
            self.diagnostics.set_phase("health_check")
            if not self._wait_for_ready():
                self.diagnostics.add_failure(
                    layer="server",
                    operation="health_check",
                    message="Server did not become ready",
                )
                self._save_diagnostics_on_error()
                msg = "Server did not become ready - see diagnostics above"
                raise RuntimeError(msg)

            # Build target info
            self._info = self._build_target_info()
            self._started = True

            total_duration = time.time() - start_time
            self.diagnostics.add_success(
                layer="testing",
                operation="start_complete",
                message=f"Target ready in {total_duration:.1f}s",
                duration=total_duration,
            )

            print("\nTarget ready:")
            print(f"  SSH: ssh {config.user}@{config.host}")
            print(f"  HTTP: {self._info.http_base}")
            print(f"  API: {self._info.api_url}")
            print("=" * 70 + "\n")

            return self._info

        except Exception as e:
            self.diagnostics.add_failure(
                layer="testing",
                operation="start",
                message=f"Start failed: {e}",
            )
            self._save_diagnostics_on_error()
            raise

    def stop(self) -> None:
        """Stop the remote target and cleanup."""
        if not self._started:
            return

        self.diagnostics.set_phase("cleanup")

        # Close SSH client if we have one
        if self._ssh_client:
            print("\nDisconnecting from remote server...")
            self._ssh_client.close()
            self._ssh_client = None

        # Remote servers keep running - we don't stop them
        print("Remote target cleanup complete (server keeps running).")
        self._started = False

    def is_ready(self) -> bool:
        """Check if the target is ready.

        Returns:
            True if server is responding
        """
        if not self._started:
            return False

        # Use deployer backend if available (deploy mode)
        if self._deployer_backend:
            return self._health_checker.is_ready(self._deployer_backend)
        # Use SSH client (connect-only mode)
        if self._ssh_client:
            return self._check_server_ready_ssh()
        return False

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Execute a command on the remote server.

        Args:
            cmd: Command to execute

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        if isinstance(cmd, list):
            # Properly escape command arguments
            cmd = " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd)

        # Use deployer backend if available (deploy mode)
        if self._deployer_backend:
            result = self._deployer_backend.run(cmd, check=False)
            return result.returncode, result.stdout, result.stderr

        # Use SSH client (connect-only mode)
        if self._ssh_client:
            try:
                _stdin, stdout, stderr = self._ssh_client.exec_command(cmd)
                exit_code = stdout.channel.recv_exit_status()
                stdout_text = stdout.read().decode()
                stderr_text = stderr.read().decode()
                return exit_code, stdout_text, stderr_text
            except Exception as e:
                msg = f"Failed to execute command: {e}"
                raise RuntimeError(msg) from e

        msg = "Target not started"
        raise RuntimeError(msg)

    def get_logs(self) -> Iterator[str]:
        """Get logs from the remote server.

        Yields:
            Log lines
        """
        if not self._ssh_client and not self._deployer_backend:
            return

        # Try to get hop3-server logs
        log_cmd = (
            "tail -n 100 /var/log/hop3-server.log 2>/dev/null || "
            "journalctl -u hop3-server -n 100 --no-pager 2>/dev/null || "
            "echo 'No logs available'"
        )

        try:
            if self._ssh_client:
                _stdin, stdout, _stderr = self._ssh_client.exec_command(log_cmd)
                for line in stdout:
                    yield line.rstrip("\n")
            elif self._deployer_backend:
                result = self._deployer_backend.run(log_cmd, check=False)
                for line in result.stdout.split("\n"):
                    yield line
        except Exception as e:
            yield f"Error getting logs: {e}"

    def save_diagnostics(self, generate_html: bool = False) -> Path:
        """Save all diagnostic information to files.

        Args:
            generate_html: If True, also generate HTML report.

        Returns:
            Path to the log directory.
        """
        return self._diagnostics_helper.save(generate_html)

    # =========================================================================
    # Private helper methods
    # =========================================================================

    def _build_ssh_connect_kwargs(self) -> dict[str, Any]:
        """Build SSH connection parameters."""
        config = self.remote_config
        connect_kwargs: dict[str, Any] = {
            "hostname": config.host,
            "port": config.port,
            "username": config.user,
            # Prefer modern ciphers, disable deprecated ones
            "disabled_algorithms": {
                "ciphers": ["3des-cbc"],  # Disable TripleDES
            },
        }

        if config.ssh_key:
            connect_kwargs["key_filename"] = config.ssh_key
        elif config.password:
            connect_kwargs["password"] = config.password
        else:
            # Try default SSH keys and ssh-agent (like regular ssh command)
            connect_kwargs["look_for_keys"] = True
            connect_kwargs["allow_agent"] = True

        return connect_kwargs

    def _check_server_ready_ssh(self) -> bool:
        """Check if server is ready via direct SSH."""
        if not self._ssh_client:
            return False

        try:
            _stdin, stdout, _stderr = self._ssh_client.exec_command(
                HEALTH_CHECK_COMMAND
            )
            output = stdout.read().decode().strip()
            return output in HEALTHY_STATUS_CODES
        except Exception:
            return False

    def _build_target_info(self) -> TargetInfo:
        """Build TargetInfo from configuration."""
        config = self.remote_config
        return TargetInfo(
            ssh_host=f"{config.user}@{config.host}",
            ssh_port=config.port,
            ssh_key=config.ssh_key,
            ssh_password=config.password,
            http_base=config.http_base or f"http://{config.host}",
            api_url=config.api_url or f"http://{config.host}:8000",
            metadata={
                "host": config.host,
                "user": config.user,
                "diagnostics": self.diagnostics,
            },
        )

    def _build_cli_command(self) -> str:
        """Build equivalent hop3-deploy CLI command for reproducibility."""
        config = self.remote_config
        deployment = self.deployment
        assert deployment is not None

        cmd_parts = ["hop3-deploy", "--host", config.host]

        if config.user != DEFAULT_SSH_ROOT_USER:
            cmd_parts.extend(["--user", config.user])
        if config.port != DEFAULT_SSH_PORT:
            cmd_parts.extend(["--port", str(config.port)])
        if deployment.source == "local":
            cmd_parts.append("--local")
        if deployment.clean:
            cmd_parts.append("--clean")
        if deployment.branch != "devel":
            cmd_parts.extend(["--branch", deployment.branch])

        return " ".join(cmd_parts)

    def _wait_for_ready(self, max_wait: int = 120) -> bool:
        """Wait for hop3-server to be ready.

        Args:
            max_wait: Maximum time to wait in seconds

        Returns:
            True if server is ready
        """
        if not self._deployer_backend:
            return False

        return self._health_checker.wait_for_ready(
            self._deployer_backend,
            timeout=max_wait,
            on_timeout=lambda: self._diagnostics_helper.collect_server_diagnostics(
                self._deployer_backend
            ),
        )

    def _save_diagnostics_on_error(self) -> None:
        """Save diagnostics to files and print to console on error."""
        self._diagnostics_helper.save_on_error()
