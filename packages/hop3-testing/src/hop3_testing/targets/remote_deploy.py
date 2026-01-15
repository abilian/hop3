# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Remote deployment target using hop3-deploy.

This target wraps the real hop3-deploy infrastructure for remote servers,
ensuring tests exercise the actual deployment path via SSH.
"""

from __future__ import annotations

import time
from typing import Any

from hop3_installer.deployer.backends.ssh import SSHDeployBackend
from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer

from .base import TargetInfo
from .constants import DEFAULT_SSH_PORT, DEFAULT_SSH_ROOT_USER
from .deploy_base import DeployTargetBase


class RemoteDeployTarget(DeployTargetBase):
    """Uses hop3-deploy to install Hop3 on a remote server via SSH.

    This target wraps the real hop3-deploy infrastructure for remote servers,
    ensuring that tests exercise the actual deployment path.

    Args:
        config: Configuration dictionary with required/optional keys:
            - host: SSH hostname (required)
            - user: SSH user (default: "root")
            - port: SSH port (default: 22)
            - local: Use local code (default: True)
            - clean: Clean before install (default: False)
            - branch: Git branch if not using local (default: "devel")
            - verbose: Show deployment output (default: False)
            - log_dir: Directory for diagnostic logs (default: test-logs)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)

        # Required config
        if "host" not in self.config:
            msg = "RemoteDeployTarget requires 'host' in configuration"
            raise ValueError(msg)

        self.host = self.config["host"]
        self.user = self.config.get("user", DEFAULT_SSH_ROOT_USER)
        self.port = self.config.get("port", DEFAULT_SSH_PORT)

    def start(self) -> TargetInfo:
        """Deploy Hop3 to the remote server using hop3-deploy.

        Returns:
            TargetInfo with connection details
        """
        start_time = time.time()

        # Initialize diagnostic context
        self.diagnostics.set_context(
            test_name=f"system-{self.host}",
            config="remote",
        )
        self.diagnostics.set_phase("setup")

        print("\n" + "=" * 70)
        print(f"Deploying Hop3 to remote server: {self.user}@{self.host}")
        print("=" * 70)

        try:
            # Find project root
            project_root = self._find_project_root()

            self.diagnostics.add_success(
                layer="testing",
                operation="find_project_root",
                message=f"Found project root at {project_root}",
            )

            # Create deployer config
            deploy_config = DeployConfig(
                host=self.host,
                ssh_user=self.user,
                ssh_port=self.port,
                use_local_code=self.use_local,
                clean_before=self.clean_before,
                branch=self.branch,
                project_root=project_root,
                verbose=self.config.get("verbose", False),
                quiet=False,
            )

            self.diagnostics.add_success(
                layer="deployer",
                operation="create_config",
                message="Created deployment configuration",
                details={
                    "host": self.host,
                    "user": self.user,
                    "local": self.use_local,
                    "clean": self.clean_before,
                    "branch": self.branch,
                },
            )

            # Print equivalent CLI command for reproducibility
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

            # Configure server for test mode (disable authentication)
            self.diagnostics.set_phase("configure_test_mode")
            if not self._configure_test_mode():
                self.diagnostics.add_failure(
                    layer="server",
                    operation="configure_test_mode",
                    message="Failed to configure test mode",
                )
                self._save_diagnostics_on_error()
                msg = "Failed to configure test mode - see diagnostics above"
                raise RuntimeError(msg)

            # Wait for server to be ready (systemd should handle service startup)
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
            print(f"  SSH: ssh {self.user}@{self.host}")
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

    def _build_cli_command(self) -> str:
        """Build equivalent hop3-deploy CLI command for reproducibility."""
        cmd_parts = ["hop3-deploy", "--host", self.host]

        if self.user != DEFAULT_SSH_ROOT_USER:
            cmd_parts.extend(["--user", self.user])
        if self.port != DEFAULT_SSH_PORT:
            cmd_parts.extend(["--port", str(self.port)])
        if self.use_local:
            cmd_parts.append("--local")
        if self.clean_before:
            cmd_parts.append("--clean")
        if self.branch and self.branch != "devel":
            cmd_parts.extend(["--branch", self.branch])

        return " ".join(cmd_parts)

    def _configure_test_mode(self) -> bool:
        """Configure the server for test mode (disable authentication).

        This sets HOP3_UNSAFE=true in the systemd service and restarts it.
        WARNING: This should only be used for testing purposes.

        Returns:
            True if configuration was successful
        """
        print("Configuring server for test mode (HOP3_UNSAFE=true)...")

        try:
            # Create systemd override directory
            result = self._deployer_backend.run(
                "mkdir -p /etc/systemd/system/hop3-server.service.d",
                check=False,
            )
            if not result.success:
                self.diagnostics.add_failure(
                    layer="server",
                    operation="create_override_dir",
                    message=f"Failed to create override directory: {result.stderr}",
                )
                return False

            # Create override file with HOP3_UNSAFE=true
            override_content = """[Service]
Environment="HOP3_UNSAFE=true"
"""
            result = self._deployer_backend.run(
                f"cat > /etc/systemd/system/hop3-server.service.d/test-mode.conf << 'EOF'\n{override_content}EOF",
                check=False,
            )
            if not result.success:
                self.diagnostics.add_failure(
                    layer="server",
                    operation="create_override_file",
                    message=f"Failed to create override file: {result.stderr}",
                )
                return False

            # Reload systemd and restart hop3-server
            result = self._deployer_backend.run(
                "systemctl daemon-reload && systemctl restart hop3-server",
                check=False,
            )
            if not result.success:
                self.diagnostics.add_failure(
                    layer="server",
                    operation="restart_service",
                    message=f"Failed to restart service: {result.stderr}",
                )
                return False

            # Wait a moment for service to start
            time.sleep(3)

            self.diagnostics.add_success(
                layer="server",
                operation="configure_test_mode",
                message="Server configured for test mode (HOP3_UNSAFE=true)",
            )
            print("  ✓ Test mode configured")
            return True

        except Exception as e:
            self.diagnostics.add_failure(
                layer="server",
                operation="configure_test_mode",
                message=f"Exception configuring test mode: {e}",
            )
            return False

    def _build_target_info(self) -> TargetInfo:
        """Build TargetInfo from deployer backend."""
        return TargetInfo(
            ssh_host=f"{self.user}@{self.host}",
            ssh_port=self.port,
            ssh_key=self.config.get("ssh_key"),
            http_base=f"http://{self.host}",
            api_url=f"http://{self.host}:8000",
            metadata={
                "host": self.host,
                "user": self.user,
                "diagnostics": self.diagnostics,
            },
        )

    def stop(self) -> None:
        """Cleanup (nothing to stop for remote servers)."""
        if not self._started:
            return

        self.diagnostics.set_phase("cleanup")
        # Remote servers keep running - we don't stop them
        print("\nRemote target cleanup complete (server keeps running).")
        self._started = False
