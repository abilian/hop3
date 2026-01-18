# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Docker deployment backend for local containers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from .base import CommandResult, DeployBackend

if TYPE_CHECKING:
    from hop3_installer.deployer.config import DeployConfig


class DockerDeployBackend(DeployBackend):
    """Backend for deploying to local Docker containers.

    This backend builds a Docker image using a Dockerfile, leveraging
    Docker's layer caching for fast rebuilds. The image is built fresh
    each time, but Docker caches unchanged layers so subsequent builds
    are nearly instant if nothing changed.
    """

    name = "docker"

    # Image name for built test image
    TEST_IMAGE = "hop3-test:latest"

    # Required ports: (host_port, container_port, description)
    REQUIRED_PORTS: ClassVar[list[tuple[int, int, str]]] = [
        (8000, 8000, "Hop3 API"),
        (8080, 80, "HTTP"),
        (8443, 443, "HTTPS"),
    ]

    def __init__(self, config: DeployConfig):
        super().__init__(config)
        self.container_name = config.docker_container
        self.image = self.TEST_IMAGE
        self._dockerfile_path = self._find_dockerfile()

    def _find_dockerfile(self) -> Path | None:
        """Find the Dockerfile for building the test image."""
        # Look for Dockerfile in known locations
        possible_paths = [
            self.config.project_root
            / "packages"
            / "hop3-installer"
            / "docker"
            / "Dockerfile.base",
            Path(__file__).parent.parent.parent.parent / "docker" / "Dockerfile.base",
        ]
        for path in possible_paths:
            if path.exists():
                return path
        return None

    def _build_image(self) -> bool:
        """Build the Docker image using docker build.

        Docker automatically uses layer caching, so unchanged layers
        are reused and rebuilds are fast.
        """
        if not self._dockerfile_path:
            print("  ✗ Dockerfile not found, falling back to direct apt-get install")
            return False

        print("  → Building Docker image (using layer cache)...")
        print(f"    Dockerfile: {self._dockerfile_path}")

        build_cmd = [
            "docker",
            "build",
            "-f",
            str(self._dockerfile_path),
            "-t",
            self.TEST_IMAGE,
            str(self.config.project_root),
        ]

        result = subprocess.run(
            build_cmd,
            capture_output=False,  # Show build output
            check=False,
        )

        if result.returncode != 0:
            print(f"  ✗ Docker build failed (exit code {result.returncode})")
            return False

        print(f"  ✓ Image built: {self.TEST_IMAGE}")
        return True

    def _docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _container_exists(self) -> bool:
        """Check if the container exists."""
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name=^{self.container_name}$", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(result.stdout.strip())

    def _container_running(self) -> bool:
        """Check if the container is running."""
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name=^{self.container_name}$", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(result.stdout.strip())

    def _remove_container(self) -> None:
        """Remove the container if it exists."""
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
            check=False,
        )

    def _check_ports_available(self) -> list[tuple[int, str, str]]:
        """Check if required ports are available.

        Returns:
            List of (port, container_name, description) for ports in use
        """
        conflicts = []

        # Check what's using our ports via docker ps
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            return conflicts

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            container_name, ports_str = parts

            # Skip our own container (will be removed anyway)
            if container_name == self.container_name:
                continue

            # Check each required port
            for host_port, _container_port, desc in self.REQUIRED_PORTS:
                # Look for port mapping like "0.0.0.0:8080->80/tcp"
                if f":{host_port}->" in ports_str or f":{host_port}/" in ports_str:
                    conflicts.append((host_port, container_name, desc))

        return conflicts

    def _report_port_conflicts(self, conflicts: list[tuple[int, str, str]]) -> None:
        """Report port conflict error to user."""
        print("  ✗ Port conflict detected!")
        print()
        print("  The following ports are already in use by other containers:")
        for port, container, desc in conflicts:
            print(f"    - Port {port} ({desc}): used by container '{container}'")
        print()
        print("  To resolve this, either:")
        print(f"    1. Stop the conflicting container: docker stop {conflicts[0][1]}")
        print(f"    2. Remove it entirely: docker rm -f {conflicts[0][1]}")
        print()

    def _start_container(self) -> bool:
        """Start a new Docker container.

        Returns:
            True if container started successfully, False otherwise.
        """
        print(f"  → Starting container from {self.image}...")
        run_result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                self.container_name,
                "-v",
                f"{self.config.project_root}:/hop3:ro",
                "-p",
                "8000:8000",
                "-p",
                "8080:80",
                "-p",
                "8443:443",
                self.image,
                "sleep",
                "infinity",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if run_result.returncode != 0:
            print("  ✗ Failed to start container")
            if run_result.stderr:
                print(f"  Error: {run_result.stderr.strip()}")
            return False
        return True

    def _wait_for_container_ready(self, timeout_seconds: int = 15) -> bool:
        """Wait for container to be running.

        Args:
            timeout_seconds: Maximum time to wait.

        Returns:
            True if container is ready, False if timeout.
        """
        import time

        for _ in range(timeout_seconds * 2):  # Check every 0.5s
            if self._container_running():
                return True
            time.sleep(0.5)

        print("  ✗ Container failed to start within timeout")
        return False

    def _install_fallback_packages(self) -> bool:
        """Install base packages when using fallback ubuntu image.

        Returns:
            True if packages installed successfully, False otherwise.
        """
        print(
            "  → Installing base packages in container (this may take a few minutes)..."
        )
        install_cmd = (
            "apt-get update && apt-get install -y python3 python3-venv git curl sudo"
        )
        exit_code = self.run_streaming(install_cmd)
        if exit_code != 0:
            print(f"  ✗ Failed to install base packages (exit code {exit_code})")
            return False
        print("  ✓ Base packages installed")
        return True

    def setup(self) -> bool:
        """Start Docker container for deployment.

        This method:
        1. Builds the Docker image using docker build (with layer caching)
        2. Starts a container from the built image

        Docker's layer caching means subsequent builds are fast if
        the Dockerfile hasn't changed.
        """
        if not self._docker_available():
            print("  ✗ Docker is not available")
            return False

        # Check for port conflicts first (before building image)
        conflicts = self._check_ports_available()
        if conflicts:
            self._report_port_conflicts(conflicts)
            return False

        # Build image using Dockerfile (with layer caching)
        image_built = self._build_image()

        # If build failed or no Dockerfile, fall back to ubuntu
        if not image_built:
            self.image = "ubuntu:24.04"
            print(f"  → Falling back to {self.image}")

        # Always remove existing container first
        self._remove_container()

        # Start and wait for container
        if not self._start_container():
            return False

        if not self._wait_for_container_ready():
            return False

        # If we fell back to ubuntu, install packages manually
        if not image_built:
            return self._install_fallback_packages()

        print("  ✓ Container ready (packages pre-installed via cached layers)")
        return True

    def teardown(self) -> None:
        """Stop and remove the container."""
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
            check=False,
        )

    def run(self, command: str, *, check: bool = True) -> CommandResult:
        """Run a command in the container."""
        docker_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash",
            "-c",
            command,
        ]

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        cmd_result = CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

        if check and not cmd_result.success:
            raise RuntimeError(
                f"Docker exec failed: {command}\n"
                f"Exit code: {result.returncode}\n"
                f"stderr: {result.stderr}"
            )

        return cmd_result

    def run_streaming(
        self, command: str, *, quiet: bool = False, log_file: Path | None = None
    ) -> int:
        """Run a command with output handling based on mode."""
        docker_cmd = [
            "docker",
            "exec",
            "-e",
            "PYTHONUNBUFFERED=1",
            "-e",
            "DEBIAN_FRONTEND=noninteractive",
            self.container_name,
            "bash",
            "-c",
            command,
        ]

        if quiet:
            # Capture output for log file
            result = subprocess.run(
                docker_cmd, capture_output=True, text=True, check=False
            )
            if log_file:
                with Path(log_file).open("a") as f:
                    f.write(f"\n=== Command: {command} ===\n")
                    if result.stdout:
                        f.write(result.stdout)
                    if result.stderr:
                        f.write(f"\n--- stderr ---\n{result.stderr}")
                    f.write(f"\n=== Exit code: {result.returncode} ===\n")
            return result.returncode

        # Stream directly to terminal
        result = subprocess.run(docker_cmd, check=False)
        return result.returncode

    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """Copy a file into the container."""
        result = subprocess.run(
            ["docker", "cp", str(local_path), f"{self.container_name}:{remote_path}"],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """Copy a directory into the container."""
        # docker cp works for directories too
        result = subprocess.run(
            ["docker", "cp", str(local_path), f"{self.container_name}:{remote_path}"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            # Fix permissions
            self.run(f"chmod -R a+rX {remote_path}", check=False)
        return result.returncode == 0

    def is_hop3_installed(self) -> bool:
        """Check if Hop3 is installed."""
        result = self.run("test -f /home/hop3/venv/bin/hop3-server", check=False)
        return result.success

    def clean(self) -> None:
        """Clean the container for fresh installation."""
        commands = [
            "systemctl stop hop3-server 2>/dev/null || true",
            "rm -rf /home/hop3",
            "userdel -r hop3 2>/dev/null || true",
            "groupdel hop3 2>/dev/null || true",
        ]

        for cmd in commands:
            self.run(cmd, check=False)

    def get_server_url(self) -> str:
        """Get the URL to access the server."""
        return "http://localhost:8000"

    def get_container_ip(self) -> str | None:
        """Get the container's internal IP address."""
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                self.container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
