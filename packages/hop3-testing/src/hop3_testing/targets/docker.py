# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Docker-based deployment target.

This module provides a consolidated Docker target that handles all Docker-based
testing scenarios:
- Pre-built image (fast app testing)
- Build from Dockerfile (custom testing)
- Deploy via hop3-deploy (system testing)
- Connect to existing container (reuse)
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import docker
from docker.errors import BuildError, ImageNotFound, NotFound

from hop3_testing.diagnostics import DiagnosticCollector

from .base import DeploymentTarget, TargetInfo
from .config import DeploymentConfig, DockerConfig
from .constants import (
    DEFAULT_HEALTH_CHECK_TIMEOUT,
    DEFAULT_READY_IMAGE_HEALTH_TIMEOUT,
)
from .helpers import (
    DiagnosticsHelper,
    DockerCommandRunner,
    DockerContainerHelper,
    DockerServiceManager,
    HealthChecker,
    find_project_root,
    run_hop3_deploy,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class DockerTarget(DeploymentTarget):
    """Docker-based target for all Docker testing scenarios.

    This consolidated target handles:
    - Pre-built images (fast app testing)
    - Build from Dockerfile (custom images)
    - Deploy via hop3-deploy (system testing)
    - Connect to existing containers (reuse)

    Examples:
        # Fast app testing with pre-built image
        target = DockerTarget(DockerConfig(image="hop3-ready:latest"))

        # Build from Dockerfile
        target = DockerTarget(DockerConfig(dockerfile=Path("Dockerfile")))

        # System testing: deploy Hop3 first
        target = DockerTarget(
            DockerConfig(),
            deployment=DeploymentConfig(source="local")
        )

        # Reuse existing container
        target = DockerTarget(
            DockerConfig(container_name="hop3-test", reuse_container=True)
        )
    """

    def __init__(
        self,
        config: DockerConfig | None = None,
        deployment: DeploymentConfig | None = None,
    ):
        """Initialize Docker target.

        Args:
            config: Docker-specific configuration
            deployment: Optional deployment configuration (if deploying Hop3)
        """
        super().__init__()

        self.docker_config = config or DockerConfig()
        self.deployment = deployment

        # Setup diagnostics
        self.diagnostics = DiagnosticCollector(
            verbose=deployment.verbose if deployment else False,
            log_dir=self.docker_config.log_dir,
        )

        # Compose helpers
        self._diagnostics_helper = DiagnosticsHelper(self.diagnostics)
        timeout = (
            DEFAULT_HEALTH_CHECK_TIMEOUT
            if deployment
            else DEFAULT_READY_IMAGE_HEALTH_TIMEOUT
        )
        self._health_checker = HealthChecker(self.diagnostics, timeout=timeout)

        # Docker client and container
        self._client: docker.DockerClient | None = None
        self._container: Any = None
        self._container_helper: DockerContainerHelper | None = None

        # Command runner for executing commands in container
        self._command_runner: DockerCommandRunner | None = None

        # State
        self._started = False
        self._we_created_container = False

    def start(self) -> TargetInfo:
        """Start the Docker target.

        The behavior depends on configuration:
        - reuse_container=True: Connect to existing container
        - deployment is set: Deploy Hop3 first via hop3-deploy
        - dockerfile is set: Build from Dockerfile
        - Otherwise: Use pre-built image

        Returns:
            TargetInfo with connection details
        """
        # Initialize diagnostics context
        self.diagnostics.set_context(
            test_name=f"docker-{self.docker_config.container_name}",
            config="docker",
        )
        self.diagnostics.set_phase("setup")

        self._client = docker.from_env()

        # Determine the mode
        if self.docker_config.reuse_container:
            return self._connect_existing()
        if self.deployment:
            return self._deploy_and_start()
        if self.docker_config.dockerfile:
            return self._build_and_start()
        return self._start_prebuilt()

    def _connect_existing(self) -> TargetInfo:
        """Connect to an existing Docker container.

        Returns:
            TargetInfo with connection details

        Raises:
            RuntimeError: If container not found or not running
        """
        assert self._client is not None  # Set by start()

        print("\n" + "=" * 70)
        print(f"Connecting to existing container: {self.docker_config.container_name}")
        print("=" * 70)

        try:
            self._container = self._client.containers.get(
                self.docker_config.container_name
            )
        except NotFound:
            msg = (
                f"Container '{self.docker_config.container_name}' not found. "
                "Start it first or set reuse_container=False"
            )
            self.diagnostics.add_failure(
                layer="docker",
                operation="find_container",
                message=msg,
            )
            raise RuntimeError(msg) from None

        self._container.reload()
        if self._container.status != "running":
            msg = f"Container '{self.docker_config.container_name}' is not running"
            self.diagnostics.add_failure(
                layer="docker",
                operation="check_status",
                message=msg,
            )
            raise RuntimeError(msg)

        self._container_helper = DockerContainerHelper(self._container)
        self._we_created_container = False

        # Wait for server to be ready
        self.diagnostics.set_phase("health_check")
        if not self._health_checker.wait_for_container(self._container):
            self._save_diagnostics_on_error()
            msg = "Server did not become ready"
            raise RuntimeError(msg)

        self._info = self._build_target_info()
        self._started = True

        self._print_ready_message()
        return self._info

    def _start_prebuilt(self) -> TargetInfo:
        """Start a pre-built Docker image (no deployment).

        Returns:
            TargetInfo with connection details
        """
        assert self._client is not None  # Set by start()

        print("\n" + "=" * 70)
        print(f"Starting pre-built container: {self.docker_config.image}")
        print("(No deployment - image should have Hop3 pre-installed)")
        print("=" * 70)

        # Check if image exists
        try:
            self._client.images.get(self.docker_config.image)
            self.diagnostics.add_success(
                layer="docker",
                operation="check_image",
                message=f"Image {self.docker_config.image} found",
            )
        except ImageNotFound:
            self.diagnostics.add_failure(
                layer="docker",
                operation="check_image",
                message=f"Image {self.docker_config.image} not found",
                details={"hint": "Build with: hop3-test build-ready-image"},
            )
            msg = f"Image {self.docker_config.image} not found"
            raise RuntimeError(msg) from None

        # Remove existing container with same name
        self._remove_existing_container()

        # Start container
        self._container = self._client.containers.run(
            self.docker_config.image,
            name=self.docker_config.container_name,
            detach=True,
            ports=self.docker_config.ports,
            remove=False,
        )
        self._container_helper = DockerContainerHelper(self._container)
        self._we_created_container = True

        self.diagnostics.add_success(
            layer="docker",
            operation="start_container",
            message=f"Container {self.docker_config.container_name} started",
        )

        # Wait for server to be ready
        self.diagnostics.set_phase("health_check")
        if not self._health_checker.wait_for_container(self._container):
            self._save_diagnostics_on_error()
            msg = "Server did not become ready"
            raise RuntimeError(msg)

        self._info = self._build_target_info()
        self._started = True

        self._print_ready_message()
        return self._info

    def _build_and_start(self) -> TargetInfo:
        """Build Docker image from Dockerfile and start container.

        Returns:
            TargetInfo with connection details
        """
        assert self._client is not None  # Set by start()

        print("\n" + "=" * 70)
        print("Building Docker image from Dockerfile...")
        print("=" * 70)

        project_root = find_project_root()
        dockerfile_path = self.docker_config.dockerfile

        if not dockerfile_path:
            # Use default E2E Dockerfile
            dockerfile_path = (
                project_root / "packages/hop3-server/tests/d_e2e/docker/Dockerfile"
            )

        if not dockerfile_path.exists():
            msg = f"Dockerfile not found at {dockerfile_path}"
            raise FileNotFoundError(msg)

        # Build distribution first
        print("Building hop3-server distribution...")
        subprocess.run(
            ["uv", "build", "packages/hop3-server"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        # Build image
        image_tag = f"hop3-e2e:{self.docker_config.container_name}"
        try:
            _image, _logs = self._client.images.build(
                path=str(project_root),
                dockerfile=str(dockerfile_path),
                tag=image_tag,
                rm=True,
                forcerm=True,
            )
            print(f"Successfully built image: {image_tag}")
        except BuildError as e:
            print(f"Build failed: {e}")
            msg = f"Failed to build Docker image: {e}"
            raise RuntimeError(msg) from e

        # Remove existing container
        self._remove_existing_container()

        # Start container
        self._container = self._client.containers.run(
            image_tag,
            name=self.docker_config.container_name,
            detach=True,
            ports=self.docker_config.ports,
            remove=False,
        )
        self._container_helper = DockerContainerHelper(self._container)
        self._we_created_container = True

        # Wait for services
        print("Waiting for services to initialize...")
        time.sleep(5)

        # Check if container is still running
        self._container.reload()
        if self._container.status != "running":
            self._dump_container_logs()
            msg = f"Container failed to start (status: {self._container.status})"
            raise RuntimeError(msg)

        # Wait for server to be ready
        self.diagnostics.set_phase("health_check")
        if not self._health_checker.wait_for_container(self._container):
            self._dump_container_logs()
            msg = "hop3-server failed to start"
            raise RuntimeError(msg)

        self._info = self._build_target_info()
        self._started = True

        self._print_ready_message()
        return self._info

    def _deploy_and_start(self) -> TargetInfo:
        """Deploy Hop3 via hop3-deploy and start container.

        Returns:
            TargetInfo with connection details
        """
        assert self._client is not None  # Set by start()
        assert self.deployment is not None  # Checked by start()

        start_time = time.time()

        print("\n" + "=" * 70)
        print("Starting Hop3 Docker container via hop3-deploy")
        print("=" * 70)

        try:
            # Run hop3-deploy via subprocess (no hop3-installer imports!)
            success, _duration = run_hop3_deploy(
                docker=True,
                container_name=self.docker_config.container_name,
                image=self.docker_config.image,
                use_local=self.deployment.source == "local",
                clean=self.deployment.clean,
                branch=self.deployment.branch,
                verbose=self.deployment.verbose,
                diagnostics=self.diagnostics,
            )

            if not success:
                self._save_diagnostics_on_error()
                msg = "hop3-deploy failed"
                raise RuntimeError(msg)

            # Get container reference after deployment
            self._container = self._client.containers.get(
                self.docker_config.container_name
            )
            self._container_helper = DockerContainerHelper(self._container)
            self._command_runner = DockerCommandRunner(self._container)

            # Start services manually (Docker doesn't have systemd)
            self.diagnostics.set_phase("service_start")
            service_manager = DockerServiceManager(
                self._command_runner, self.diagnostics
            )
            if not service_manager.start_all():
                self._save_diagnostics_on_error()
                msg = "Failed to start services"
                raise RuntimeError(msg)

            # Wait for server to be ready
            self.diagnostics.set_phase("health_check")
            if not self._health_checker.wait_for_ready(
                self._command_runner,
                timeout=DEFAULT_HEALTH_CHECK_TIMEOUT,
                on_timeout=self._collect_deploy_diagnostics,
            ):
                self._save_diagnostics_on_error()
                msg = "Server did not become ready"
                raise RuntimeError(msg)

            self._we_created_container = True
            self._info = self._build_target_info()
            self._started = True

            # Log completion
            total_duration = time.time() - start_time
            self.diagnostics.add_success(
                layer="testing",
                operation="start_complete",
                message=f"Target ready in {total_duration:.1f}s",
                duration=total_duration,
            )

            self._print_ready_message()
            return self._info

        except Exception as e:
            if self.diagnostics:
                self.diagnostics.add_failure(
                    layer="testing",
                    operation="start",
                    message=f"Start failed: {e}",
                )
            self._save_diagnostics_on_error()
            raise

    def _build_target_info(self) -> TargetInfo:
        """Build TargetInfo from container."""
        assert self._container_helper is not None  # Set before calling this method

        ssh_port = self._container_helper.get_mapped_port(22)
        http_port = self._container_helper.get_mapped_port(80)
        api_port = self._container_helper.get_mapped_port(8000)

        # Get container's internal IP for SSH (used when no host port mapping)
        container_ip = self._get_container_ip()

        # Determine SSH host: prefer host-mapped port, fall back to container IP
        if ssh_port:
            ssh_host = "hop3@localhost"
            effective_ssh_port = ssh_port
        elif container_ip:
            # No SSH port mapped to host, use container's internal IP
            ssh_host = f"hop3@{container_ip}"
            effective_ssh_port = 22
        else:
            ssh_host = ""
            effective_ssh_port = 0

        # Try to extract SSH key (may fail if container doesn't have hop3 user)
        ssh_key_path: Path | None = None
        if effective_ssh_port:
            try:
                ssh_key_path = self._container_helper.extract_ssh_key()
            except Exception:
                pass  # SSH not available in this container

        # Build URLs based on available ports
        http_base = f"http://localhost:{http_port}" if http_port else ""
        api_url = f"http://localhost:{api_port}" if api_port else ""

        return TargetInfo(
            ssh_host=ssh_host,
            ssh_port=effective_ssh_port,
            ssh_key=str(ssh_key_path) if ssh_key_path else None,
            http_base=http_base,
            api_url=api_url,
            metadata={
                "container_id": self._container_helper.container_id,
                "container_name": self._container_helper.name,
            },
        )

    def _get_container_ip(self) -> str | None:
        """Get the container's internal IP address."""
        try:
            self._container.reload()
            networks = self._container.attrs["NetworkSettings"]["Networks"]
            # Get IP from first network (usually "bridge")
            for network_info in networks.values():
                ip = network_info.get("IPAddress")
                if ip:
                    return ip
        except Exception:
            pass
        return None

    def _remove_existing_container(self) -> None:
        """Remove any existing container with the same name."""
        assert self._client is not None  # Set by start()

        try:
            existing = self._client.containers.get(self.docker_config.container_name)
            print(f"Removing existing container: {self.docker_config.container_name}")
            existing.remove(force=True)
        except NotFound:
            pass

    def _dump_container_logs(self) -> None:
        """Dump container logs for debugging."""
        if not self._container:
            return

        logs = self._container.logs().decode()

        # Add to diagnostics for reports
        self.diagnostics.add_debug(
            layer="docker",
            operation="container_logs",
            message="Container logs captured",
            details={"logs": logs},
        )

        # Still print for immediate feedback
        print("\nContainer logs:")
        print(logs)

    def _collect_deploy_diagnostics(self) -> None:
        """Collect diagnostics when health check times out."""
        if not self._command_runner:
            print("  Cannot collect diagnostics - no command runner")
            return

        print("  Collecting diagnostics...")
        try:
            result = self._command_runner.run(
                "ss -tlnp | grep 8000 || echo 'No listener on 8000'",
                check=False,
            )
            print(f"  Port 8000: {result.stdout.strip()}")

            result = self._command_runner.run(
                "tail -30 /home/hop3/hop3-server.log 2>/dev/null || echo 'No log'",
                check=False,
            )
            print(f"  hop3-server log:\n{result.stdout}")

            result = self._command_runner.run(
                "ps aux | grep -E 'hop3|nginx|uwsgi' | grep -v grep || echo 'No processes'",
                check=False,
            )
            print(f"  Running processes:\n{result.stdout}")

        except Exception as e:
            print(f"  Error collecting diagnostics: {e}")

    def _save_diagnostics_on_error(self) -> None:
        """Save diagnostics on error."""
        self._diagnostics_helper.save_on_error()

    def _print_ready_message(self) -> None:
        """Print ready message with connection info."""
        assert self._info is not None  # Set before calling this method

        print("\nTarget ready:")
        print(f"  HTTP: {self._info.http_base}")
        print(f"  API: {self._info.api_url}")
        if self._info.ssh_key:
            print(
                f"  SSH: ssh -i {self._info.ssh_key} -p {self._info.ssh_port} hop3@localhost"
            )
        print("=" * 70 + "\n")

    def stop(self) -> None:
        """Stop and cleanup the Docker target."""
        if not self._started:
            return

        self.diagnostics.set_phase("cleanup")

        # Don't stop containers we didn't create
        if not self._we_created_container:
            print("\nDisconnecting (not stopping container we didn't create)...")
            self._started = False
            return

        print("\nStopping container...")

        try:
            if self._container_helper:
                self._container_helper.stop_and_remove()

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

    def is_ready(self) -> bool:
        """Check if the target is ready."""
        if not self._started:
            return False

        if self._command_runner:
            return self._health_checker.is_ready(self._command_runner)
        if self._container:
            return self._health_checker.is_container_ready(self._container)
        return False

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Execute a command on the target.

        Args:
            cmd: Command to execute

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        if isinstance(cmd, list):
            cmd = " ".join(cmd)

        if self._command_runner:
            result = self._command_runner.run(cmd, check=False)
            return result.returncode, result.stdout, result.stderr
        if self._container_helper:
            result = self._container_helper.exec_run(cmd, demux=True)
            stdout = result.output[0].decode() if result.output[0] else ""
            stderr = result.output[1].decode() if result.output[1] else ""
            return result.exit_code, stdout, stderr

        msg = "Target not started"
        raise RuntimeError(msg)

    def get_logs(self) -> Iterator[str]:
        """Get container logs.

        Yields:
            Log lines
        """
        if self._container_helper:
            for line in self._container_helper.get_logs(stream=True):
                yield line.decode()

    def save_diagnostics(self, generate_html: bool = False) -> Path:
        """Save diagnostic information to files.

        Args:
            generate_html: If True, also generate HTML report

        Returns:
            Path to the log directory
        """
        return self._diagnostics_helper.save(generate_html)
