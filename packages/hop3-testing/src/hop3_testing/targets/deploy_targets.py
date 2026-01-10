# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deployment targets that wrap hop3-deploy.

These targets use the real hop3-deploy infrastructure instead of
building custom Docker images. This ensures tests exercise the
actual deployment path.

Classes:
    DockerDeployTarget: Uses hop3-deploy --docker for system testing
    RemoteDeployTarget: Uses hop3-deploy --host X for remote system testing
    ReadyTarget: Uses pre-built image for app testing (no deployment)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..diagnostics import DiagnosticCollector
from .base import DeploymentTarget, TargetInfo

if TYPE_CHECKING:
    pass


class DockerDeployTarget(DeploymentTarget):
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
        self.config = config or {}

        # Setup diagnostics with file logging
        log_dir = self.config.get("log_dir")
        self.diagnostics = DiagnosticCollector(
            verbose=self.config.get("verbose", False),
            log_dir=Path(log_dir) if log_dir else None,
        )

        # Deployment options
        self.use_local = self.config.get("local", True)
        self.clean_before = self.config.get("clean", False)
        self.branch = self.config.get("branch", "devel")
        self.container_name = self.config.get("container_name", "hop3-test")

        # State
        self._deployer_backend = None
        self._started = False

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
            # Import deployer components
            from hop3_installer.deployer.backends.docker import DockerDeployBackend
            from hop3_installer.deployer.config import DeployConfig
            from hop3_installer.deployer.deploy import Deployer

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
                docker_image="ubuntu:24.04",
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

            print(f"\nTarget ready:")
            print(f"  HTTP: {self._info.http_base}")
            print(f"  API: {self._info.api_url}")
            print("=" * 70 + "\n")

            return self._info

        except ImportError as e:
            self.diagnostics.add_failure(
                layer="testing",
                operation="import_deployer",
                message=f"Failed to import hop3-deploy: {e}",
            )
            self._save_diagnostics_on_error()
            raise

        except Exception as e:
            self.diagnostics.add_failure(
                layer="testing",
                operation="start",
                message=f"Start failed: {e}",
            )
            self._save_diagnostics_on_error()
            raise

    def _save_diagnostics_on_error(self) -> None:
        """Save diagnostics to files and print to console on error."""
        print(self.diagnostics.dump_to_console())
        log_path = self.diagnostics.save_logs()
        print(f"\nDiagnostic logs saved to: {log_path}")

    def _find_project_root(self) -> Path:
        """Find the project root directory."""
        current = Path(__file__).parent
        while current != current.parent:
            if (current / "pyproject.toml").exists() and (
                current / "packages"
            ).exists():
                return current
            current = current.parent

        msg = "Could not find project root"
        raise RuntimeError(msg)

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
            if result.returncode != 0 and "already running" not in result.stderr.lower():
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
                "export HOP3_SECRET_KEY=\"e2e-test-secret-key-do-not-use-in-production\" && "
                "export HOP3_UNSAFE=\"true\" && "
                "export HOP3_DB_URL=\"sqlite:////home/hop3/hop3.db\" && "
                "export ACME_ENGINE=\"self-signed\" && "
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

        Args:
            max_wait: Maximum time to wait in seconds

        Returns:
            True if server is ready
        """
        print("Waiting for hop3-server to be ready...")
        start_time = time.time()
        last_status = "unknown"

        while time.time() - start_time < max_wait:
            try:
                # Check server health via deployer backend
                result = self._deployer_backend.run(
                    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'",
                    check=False,
                )
                last_status = result.stdout.strip()

                # Accept any valid HTTP response (2xx, 3xx, 4xx all mean server is running)
                # Only 000 (connection failed) or 5xx means server isn't ready
                if any(code in result.stdout for code in ["200", "301", "302", "303", "307", "308", "404"]):
                    self.diagnostics.add_success(
                        layer="server",
                        operation="health_check",
                        message="hop3-server is responding",
                        duration=time.time() - start_time,
                        details={"status_code": last_status},
                    )
                    print(f"✓ hop3-server is responding (status: {last_status})")
                    return True

                # Log progress every 10 seconds
                elapsed = int(time.time() - start_time)
                if elapsed > 0 and elapsed % 10 == 0:
                    print(f"  ... waiting ({elapsed}s), last status: {last_status}")

            except Exception as e:
                self.diagnostics.add_failure(
                    layer="server",
                    operation="health_check_attempt",
                    message=f"Health check failed: {e}",
                )

            time.sleep(2)

        # Collect diagnostic info on failure
        print(f"  Health check timed out after {max_wait}s. Last status: {last_status}")

        # Get more info about what's happening
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

        self._collect_server_diagnostics()
        return False

    def _collect_server_diagnostics(self) -> None:
        """Collect diagnostic information from the server."""
        self.diagnostics.set_phase("diagnostics")
        try:
            # Check systemd service
            result = self._deployer_backend.run(
                "systemctl status hop3-server 2>&1 || true",
                check=False,
            )
            # Use add_success to store info (not a failure, just diagnostic data)
            self.diagnostics.add_success(
                layer="server",
                operation="systemd_status",
                message="hop3-server systemd status collected",
                stdout=result.stdout,
                stderr=result.stderr,
                details={"type": "diagnostic_info"},
            )

            # Check server logs
            result = self._deployer_backend.run(
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

            # Check nginx
            result = self._deployer_backend.run(
                "systemctl status nginx 2>&1 || true",
                check=False,
            )
            self.diagnostics.add_success(
                layer="server",
                operation="nginx_status",
                message="nginx systemd status collected",
                stdout=result.stdout,
                details={"type": "diagnostic_info"},
            )

            # Check listening ports
            result = self._deployer_backend.run(
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

    def save_diagnostics(self, generate_html: bool = False) -> Path:
        """Save all diagnostic information to files.

        Args:
            generate_html: If True, also generate HTML report.

        Returns:
            Path to the log directory.
        """
        log_path = self.diagnostics.save_logs()

        if generate_html:
            html_path = self.diagnostics.generate_html_report()
            print(f"HTML report saved to: {html_path}")

        return log_path

    def is_ready(self) -> bool:
        """Check if the container is ready."""
        if not self._started or not self._deployer_backend:
            return False

        try:
            result = self._deployer_backend.run(
                "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'",
                check=False,
            )
            # Accept any valid HTTP response
            return any(code in result.stdout for code in ["200", "301", "302", "303", "307", "308", "404"])
        except Exception:
            return False

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Execute a command in the container."""
        if not self._deployer_backend:
            msg = "Container not started"
            raise RuntimeError(msg)

        if isinstance(cmd, list):
            cmd = " ".join(cmd)

        result = self._deployer_backend.run(cmd, check=False)
        return result.returncode, result.stdout, result.stderr


class ReadyTarget(DeploymentTarget):
    """Uses a pre-built Docker image for app testing.

    This target does NOT deploy Hop3 - it expects the image to already
    have Hop3 installed and ready. This is used for:
    - App testing (testing apps, not Hop3)
    - Fast iteration (skip 5+ minute installation)
    - CI pipelines (use cached image)

    Args:
        config: Configuration dictionary with optional keys:
            - image: Docker image to use (default: "hop3-ready:latest")
            - container_name: Override container name
            - verbose: Verbose output (default: False)
            - log_dir: Directory for diagnostic logs
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

        self.image = self.config.get("image", "hop3-ready:latest")
        self.container_name = self.config.get("container_name", "hop3-app-test")

        self._container = None
        self._started = False

    def start(self) -> TargetInfo:
        """Start the pre-built container.

        Returns:
            TargetInfo with connection details
        """
        import docker

        # Initialize diagnostic context
        self.diagnostics.set_context(
            test_name=f"apps-{self.container_name}",
            config="ready",
        )
        self.diagnostics.set_phase("setup")

        print("\n" + "=" * 70)
        print(f"Starting pre-built container: {self.image}")
        print("(No deployment - image should have Hop3 pre-installed)")
        print("=" * 70)

        try:
            client = docker.from_env()

            # Check if image exists
            try:
                client.images.get(self.image)
                self.diagnostics.add_success(
                    layer="docker",
                    operation="check_image",
                    message=f"Image {self.image} found",
                )
            except docker.errors.ImageNotFound:
                self.diagnostics.add_failure(
                    layer="docker",
                    operation="check_image",
                    message=f"Image {self.image} not found",
                    details={
                        "hint": "Build with: hop3-test-new build-ready-image",
                    },
                )
                # Don't save here - let the outer exception handler do it
                msg = f"Image {self.image} not found. Build it with: hop3-test-new build-ready-image"
                raise RuntimeError(msg) from None

            # Remove any existing container with the same name
            try:
                existing = client.containers.get(self.container_name)
                print(f"Removing existing container: {self.container_name}")
                existing.remove(force=True)
            except docker.errors.NotFound:
                pass  # No existing container, good

            # Start container
            self._container = client.containers.run(
                self.image,
                name=self.container_name,
                detach=True,
                ports={
                    "22/tcp": None,
                    "80/tcp": None,
                    "8000/tcp": None,
                },
                remove=False,
            )

            self.diagnostics.add_success(
                layer="docker",
                operation="start_container",
                message=f"Container {self.container_name} started",
            )

            # Wait for server to be ready
            self.diagnostics.set_phase("health_check")
            if not self._wait_for_ready():
                self.diagnostics.add_failure(
                    layer="server",
                    operation="health_check",
                    message="Server did not become ready",
                )
                self._save_diagnostics_on_error()
                msg = "Server did not become ready"
                raise RuntimeError(msg)

            self._info = self._build_target_info()
            self._started = True

            print(f"\nTarget ready:")
            print(f"  HTTP: {self._info.http_base}")
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

    def _save_diagnostics_on_error(self) -> None:
        """Save diagnostics to files and print to console on error."""
        print(self.diagnostics.dump_to_console())
        log_path = self.diagnostics.save_logs()
        print(f"\nDiagnostic logs saved to: {log_path}")

    def _wait_for_ready(self, max_wait: int = 60) -> bool:
        """Wait for server to be ready."""
        print("Waiting for hop3-server to be ready...")
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                self._container.reload()
                if self._container.status != "running":
                    return False

                result = self._container.exec_run(
                    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'"
                )
                if b"200" in result.output or b"404" in result.output:
                    print("✓ hop3-server is responding")
                    return True

            except Exception:
                pass

            time.sleep(2)

        return False

    def _build_target_info(self) -> TargetInfo:
        """Build TargetInfo from container."""
        self._container.reload()
        ports = self._container.attrs["NetworkSettings"]["Ports"]

        ssh_port = int(ports["22/tcp"][0]["HostPort"])
        http_port = int(ports["80/tcp"][0]["HostPort"])
        api_port = int(ports["8000/tcp"][0]["HostPort"])

        # Extract SSH key
        ssh_key_path = self._extract_ssh_key()

        return TargetInfo(
            ssh_host="hop3@localhost",
            ssh_port=ssh_port,
            ssh_key=str(ssh_key_path) if ssh_key_path else None,
            http_base=f"http://localhost:{http_port}",
            api_url=f"http://localhost:{api_port}",
            metadata={
                "container_id": self._container.id,
                "container_name": self._container.name,
            },
        )

    def _extract_ssh_key(self) -> Path | None:
        """Extract SSH key from container."""
        try:
            result = self._container.exec_run("cat /home/hop3/.ssh/id_rsa")
            if result.exit_code == 0:
                key_path = Path("/tmp") / f"hop3-ready-key-{self._container.short_id}"
                key_path.write_text(result.output.decode())
                key_path.chmod(0o600)
                return key_path
        except Exception:
            pass
        return None

    def stop(self) -> None:
        """Stop and remove the container."""
        if not self._container:
            return

        self.diagnostics.set_phase("cleanup")
        print("\nStopping container...")
        try:
            self._container.reload()
            if self._container.status == "running":
                self._container.stop(timeout=10)
            self._container.remove(force=True)
            self.diagnostics.add_success(
                layer="docker",
                operation="teardown",
                message="Container stopped and removed",
            )
        except Exception as e:
            self.diagnostics.add_failure(
                layer="docker",
                operation="teardown",
                message=f"Error stopping container: {e}",
            )
            print(f"Warning: Error stopping container: {e}")

        self._started = False
        print("Container stopped.")

    def save_diagnostics(self, generate_html: bool = False) -> Path:
        """Save all diagnostic information to files.

        Args:
            generate_html: If True, also generate HTML report.

        Returns:
            Path to the log directory.
        """
        log_path = self.diagnostics.save_logs()

        if generate_html:
            html_path = self.diagnostics.generate_html_report()
            print(f"HTML report saved to: {html_path}")

        return log_path

    def is_ready(self) -> bool:
        """Check if the container is ready."""
        if not self._container:
            return False

        try:
            self._container.reload()
            if self._container.status != "running":
                return False

            result = self._container.exec_run(
                "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'"
            )
            return b"200" in result.output or b"404" in result.output
        except Exception:
            return False

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Execute a command in the container."""
        if not self._container:
            msg = "Container not started"
            raise RuntimeError(msg)

        if isinstance(cmd, list):
            cmd = " ".join(cmd)

        result = self._container.exec_run(cmd, demux=True)
        stdout = result.output[0].decode() if result.output[0] else ""
        stderr = result.output[1].decode() if result.output[1] else ""

        return result.exit_code, stdout, stderr
