# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Docker deployment target using hop3-deploy.

This target wraps the real hop3-deploy infrastructure to create Docker containers
for system testing, ensuring tests exercise the actual deployment path.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from hop3_installer.deployer.backends.docker import DockerDeployBackend
from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer

from .base import TargetInfo
from .constants import DEFAULT_CONTAINER_NAME, DEFAULT_DOCKER_IMAGE
from .deploy_base import DeployTargetBase


class DockerDeployTarget(DeployTargetBase):
    """Uses hop3-deploy to create Docker containers for system testing.

    This target wraps the real hop3-deploy infrastructure, ensuring that
    tests exercise the actual deployment path including:
    - hop3-install server (full installation)
    - systemd service setup
    - nginx configuration
    - etc.

    Args:
        config: Configuration dictionary with optional keys:
            - local: Use local code (default: True)
            - clean: Clean before install (default: False)
            - branch: Git branch if not using local (default: "devel")
            - verbose: Show deployment output (default: False)
            - container_name: Override container name
            - log_dir: Directory for diagnostic logs (default: test-logs)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.container_name = self.config.get("container_name", DEFAULT_CONTAINER_NAME)

    def start(self) -> TargetInfo:
        """Start the Docker container using hop3-deploy.

        Returns:
            TargetInfo with connection details
        """
        start_time = time.time()

        # Initialize diagnostic context
        self.diagnostics.set_context(
            test_name=f"system-{self.container_name}",
            config="docker",
        )
        self.diagnostics.set_phase("setup")

        print("\n" + "=" * 70)
        print("Starting Hop3 Docker container via hop3-deploy")
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
                use_docker=True,
                docker_container=self.container_name,
                docker_image=DEFAULT_DOCKER_IMAGE,
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
                    "local": self.use_local,
                    "clean": self.clean_before,
                    "branch": self.branch,
                    "container": self.container_name,
                },
            )

            # Create backend and deployer
            self._deployer_backend = DockerDeployBackend(deploy_config)
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

            # Start services manually (Docker doesn't have systemd)
            self.diagnostics.set_phase("service_start")
            if not self._start_services_manually():
                self.diagnostics.add_failure(
                    layer="server",
                    operation="service_start",
                    message="Failed to start services manually",
                )
                self._save_diagnostics_on_error()
                msg = "Failed to start services - see diagnostics above"
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

    def _start_services_manually(self) -> bool:
        """Start services manually since Docker doesn't have systemd.

        This mimics what the existing E2E Docker infrastructure does with
        supervisor, but runs the services directly in the background.

        Returns:
            True if all services started successfully
        """
        print("Starting services manually (Docker has no systemd)...")

        try:
            # Ensure SSH server is installed and configured
            print("  Setting up SSH server...")
            result = self._deployer_backend.run(
                """
                # Install openssh-server if not present
                if ! command -v sshd &> /dev/null; then
                    apt-get update -qq && apt-get install -y -qq openssh-server
                fi && \
                # Setup SSH keys for hop3 user
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
                # Configure SSH
                mkdir -p /var/run/sshd && \
                sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config 2>/dev/null || true && \
                sed -i 's/#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config 2>/dev/null || true
                """,
                check=False,
            )
            self.diagnostics.add_success(
                layer="server",
                operation="setup_ssh",
                message="SSH server configured",
                stdout=result.stdout,
            )

            # Start SSH daemon (needed for deployments)
            print("  Starting SSH daemon...")
            result = self._deployer_backend.run(
                "/usr/sbin/sshd || echo 'sshd may already be running'",
                check=False,
            )
            # Give sshd a moment to start
            time.sleep(1)

            # Verify sshd is running
            result = self._deployer_backend.run(
                "pgrep sshd || echo 'NO_SSHD'",
                check=False,
            )
            if "NO_SSHD" in result.stdout:
                self.diagnostics.add_failure(
                    layer="server",
                    operation="start_sshd",
                    message="sshd failed to start",
                    stdout=result.stdout,
                )
            else:
                self.diagnostics.add_success(
                    layer="server",
                    operation="start_sshd",
                    message="sshd started",
                )

            # Start nginx in background
            print("  Starting nginx...")
            result = self._deployer_backend.run(
                "nginx || nginx -g 'daemon off;' &",
                check=False,
            )
            if (
                result.returncode != 0
                and "already running" not in result.stderr.lower()
            ):
                self.diagnostics.add_failure(
                    layer="server",
                    operation="start_nginx",
                    message=f"Failed to start nginx: {result.stderr}",
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
                # Continue anyway - nginx might already be running
            else:
                self.diagnostics.add_success(
                    layer="server",
                    operation="start_nginx",
                    message="nginx started",
                )

            # Start PostgreSQL if installed
            print("  Starting PostgreSQL...")
            result = self._deployer_backend.run(
                "su - postgres -c 'pg_ctlcluster 16 main start' 2>/dev/null || "
                "service postgresql start 2>/dev/null || true",
                check=False,
            )
            self.diagnostics.add_success(
                layer="server",
                operation="start_postgres",
                message="PostgreSQL start attempted",
                stdout=result.stdout,
            )

            # Start uwsgi emperor in background (as hop3 user)
            print("  Starting uwsgi emperor...")
            # Ensure log directory exists and uwsgi stats socket dir
            result = self._deployer_backend.run(
                "mkdir -p /var/log/uwsgi && chown -R hop3:hop3 /var/log/uwsgi && "
                "mkdir -p /tmp && chmod 1777 /tmp",
                check=False,
            )
            # Start uwsgi as hop3 user - using the venv-installed uwsgi
            # Matching systemd service: /home/hop3/venv/bin/uwsgi --emperor /home/hop3/uwsgi-enabled
            result = self._deployer_backend.run(
                "su - hop3 -c '"
                "nohup /home/hop3/venv/bin/uwsgi --emperor /home/hop3/uwsgi-enabled "
                "--stats /tmp/hop3-uwsgi-stats.sock "
                "> /var/log/uwsgi/emperor.log 2>&1 &'",
                check=False,
            )
            # Give uwsgi a moment to start
            time.sleep(2)
            # Verify uwsgi is running
            result = self._deployer_backend.run(
                "pgrep -f 'uwsgi.*emperor' || echo 'NO_UWSGI'",
                check=False,
            )
            if "NO_UWSGI" in result.stdout:
                # Try to get error from log
                log_result = self._deployer_backend.run(
                    "cat /var/log/uwsgi/emperor.log 2>/dev/null || echo 'No log'",
                    check=False,
                )
                self.diagnostics.add_failure(
                    layer="server",
                    operation="start_uwsgi",
                    message="uwsgi emperor failed to start",
                    stdout=log_result.stdout,
                )
            else:
                self.diagnostics.add_success(
                    layer="server",
                    operation="start_uwsgi",
                    message="uwsgi emperor started",
                )

            # Start hop3-server in background
            print("  Starting hop3-server...")
            result = self._deployer_backend.run(
                "su - hop3 -c '"
                'export HOP3_SECRET_KEY="e2e-test-secret-key-do-not-use-in-production" && '
                'export HOP3_UNSAFE="true" && '
                'export HOP3_DB_URL="sqlite:////home/hop3/hop3.db" && '
                'export ACME_ENGINE="self-signed" && '
                "nohup /home/hop3/venv/bin/hop3-server serve "
                "> /home/hop3/hop3-server.log 2>&1 &'",
                check=False,
            )
            self.diagnostics.add_success(
                layer="server",
                operation="start_hop3_server",
                message="hop3-server started",
            )

            # Give services a moment to initialize
            time.sleep(3)

            # Check if hop3-server process is running
            result = self._deployer_backend.run(
                "pgrep -f 'hop3-server serve' || echo 'NOT_RUNNING'",
                check=False,
            )
            if "NOT_RUNNING" in result.stdout:
                # Try to get error from log
                log_result = self._deployer_backend.run(
                    "tail -50 /home/hop3/hop3-server.log 2>/dev/null || echo 'No log'",
                    check=False,
                )
                self.diagnostics.add_failure(
                    layer="server",
                    operation="verify_hop3_server",
                    message="hop3-server process not running",
                    stdout=log_result.stdout,
                )
                return False

            self.diagnostics.add_success(
                layer="server",
                operation="verify_services",
                message="All services started successfully",
            )
            print("  ✓ Services started")
            return True

        except Exception as e:
            self.diagnostics.add_failure(
                layer="server",
                operation="start_services",
                message=f"Exception starting services: {e}",
            )
            return False

    def _wait_for_ready(self, max_wait: int = 120) -> bool:
        """Wait for hop3-server to be ready.

        Extends base class to add Docker-specific diagnostics on timeout.

        Args:
            max_wait: Maximum time to wait in seconds

        Returns:
            True if server is ready
        """
        self._health_checker.timeout = max_wait
        return self._health_checker.wait_for_ready(
            self._deployer_backend,
            on_timeout=self._on_health_timeout,
        )

    def _on_health_timeout(self) -> None:
        """Called when health check times out - collect Docker diagnostics."""
        self._collect_docker_diagnostics()
        self._collect_server_diagnostics()

    def _collect_docker_diagnostics(self) -> None:
        """Collect Docker-specific diagnostic information."""
        print("  Collecting additional diagnostics...")
        try:
            # Check what's actually listening on port 8000
            result = self._deployer_backend.run(
                "ss -tlnp | grep 8000 || echo 'No listener on 8000'",
                check=False,
            )
            print(f"  Port 8000: {result.stdout.strip()}")

            # Check hop3-server log
            result = self._deployer_backend.run(
                "tail -30 /home/hop3/hop3-server.log 2>/dev/null || echo 'No log file'",
                check=False,
            )
            print(f"  hop3-server log:\n{result.stdout}")

            # Check process list
            result = self._deployer_backend.run(
                "ps aux | grep -E 'hop3|nginx|uwsgi' | grep -v grep || echo 'No hop3 processes'",
                check=False,
            )
            print(f"  Running processes:\n{result.stdout}")

            # Try to make a full request to see what we get
            result = self._deployer_backend.run(
                "curl -v http://localhost:8000/ 2>&1 | head -30",
                check=False,
            )
            print(f"  Full curl output:\n{result.stdout}")

        except Exception as e:
            print(f"  Error collecting diagnostics: {e}")

    def _build_target_info(self) -> TargetInfo:
        """Build TargetInfo from deployer backend."""
        # The deployer backend exposes the server at localhost:8000
        server_url = self._deployer_backend.get_server_url()

        # For SSH access, we need to get container IP and SSH key
        container_ip = self._deployer_backend.get_container_ip()

        # Extract SSH key from container
        ssh_key_path = self._extract_ssh_key()

        return TargetInfo(
            ssh_host=f"hop3@{container_ip}" if container_ip else "hop3@localhost",
            ssh_port=22,
            ssh_key=str(ssh_key_path) if ssh_key_path else None,
            http_base="http://localhost:8080",  # nginx port forwarded by Docker backend
            api_url=server_url,
            metadata={
                "container_name": self.container_name,
                "diagnostics": self.diagnostics,
            },
        )

    def _extract_ssh_key(self) -> Path | None:
        """Extract SSH key from container."""
        try:
            result = self._deployer_backend.run(
                "cat /home/hop3/.ssh/id_rsa 2>/dev/null || true",
                check=False,
            )

            if result.success and result.stdout.strip():
                key_path = Path("/tmp") / f"hop3-test-key-{self.container_name}"
                key_path.write_text(result.stdout)
                key_path.chmod(0o600)
                return key_path

        except Exception as e:
            self.diagnostics.add_failure(
                layer="testing",
                operation="extract_ssh_key",
                message=f"Failed to extract SSH key: {e}",
            )

        return None

    def stop(self) -> None:
        """Stop and remove the container."""
        if not self._started:
            return

        self.diagnostics.set_phase("cleanup")
        print("\nStopping container...")
        try:
            if self._deployer_backend:
                self._deployer_backend.teardown()
                self.diagnostics.add_success(
                    layer="docker",
                    operation="teardown",
                    message="Container stopped and removed",
                )
        except Exception as e:
            self.diagnostics.add_failure(
                layer="docker",
                operation="teardown",
                message=f"Failed to stop container: {e}",
            )

        self._started = False
        print("Container stopped.")
