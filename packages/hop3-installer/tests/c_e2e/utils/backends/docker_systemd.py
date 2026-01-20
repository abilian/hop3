# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Docker backend with systemd support for full service testing."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from hop3_installer.common import CommandResult

from ..common import log_debug, log_error, log_info, log_success, log_warning
from .base import Backend

# The systemd-enabled image name
SYSTEMD_IMAGE = "hop3-test-systemd:latest"
CONTAINER_NAME = "hop3-test-systemd"


class DockerSystemdBackend(Backend):
    """Backend for testing in Docker containers with systemd support.

    This backend runs tests inside Docker containers with full systemd
    support, enabling testing of services like nginx, postgresql, and
    hop3-server systemd units.

    Requires:
    - Docker with --privileged support
    - Pre-built hop3-test-systemd:latest image
    """

    name = "docker-systemd"
    supports_systemd = True

    def __init__(self, installer_dir: Path | None = None):
        """Initialize Docker systemd backend.

        Args:
            installer_dir: Path to installer directory (for mounting)
        """
        self.installer_dir = installer_dir or Path(__file__).parent.parent.parent.parent
        self.container_name = CONTAINER_NAME
        self.image = SYSTEMD_IMAGE

    def _docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                check=False,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _image_exists(self) -> bool:
        """Check if the systemd image exists."""
        result = subprocess.run(
            ["docker", "images", "-q", self.image],
            check=False,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def _build_image(self) -> bool:
        """Build the systemd-enabled Docker image."""
        # Try to find Dockerfile.systemd relative to the test directory
        dockerfile = (
            Path(__file__).parent.parent.parent.parent / "docker" / "Dockerfile.systemd"
        )
        if not dockerfile.exists():
            # Try relative to installer_dir
            dockerfile = self.installer_dir / "docker" / "Dockerfile.systemd"
        if not dockerfile.exists():
            log_error(f"Dockerfile.systemd not found at {dockerfile}")
            return False

        log_info("Building hop3-test-systemd image...")
        try:
            subprocess.run(
                [
                    "docker",
                    "build",
                    "-f",
                    str(dockerfile),
                    "-t",
                    self.image,
                    str(dockerfile.parent),
                ],
                check=True,
                capture_output=True,
                timeout=600,  # 10 minutes for build
            )
            log_success("Image built successfully")
            return True
        except subprocess.CalledProcessError as e:
            log_error(f"Failed to build image: {e.stderr[:500] if e.stderr else ''}")
            return False
        except subprocess.TimeoutExpired:
            log_error("Image build timed out")
            return False

    def _container_exists(self) -> bool:
        """Check if the container exists."""
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={self.container_name}", "-q"],
            check=False,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def _container_running(self) -> bool:
        """Check if the container is running."""
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={self.container_name}", "-q"],
            check=False,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def _remove_container(self) -> bool:
        """Remove existing container with retry."""
        if not self._container_exists():
            return True

        log_debug(f"Removing existing container: {self.container_name}")
        for _attempt in range(10):
            subprocess.run(
                ["docker", "rm", "-f", self.container_name],
                check=False,
                capture_output=True,
            )
            time.sleep(1)
            if not self._container_exists():
                return True
        return False

    def setup(self) -> bool:
        """Start Docker container with systemd for testing."""
        if not self._docker_available():
            log_error("Docker is not available or not running")
            return False

        # Build image if needed
        if not self._image_exists():
            log_warning(f"Image {self.image} not found, building...")
            if not self._build_image():
                return False

        log_info(f"Starting container: {self.container_name} (image: {self.image})")

        # Remove existing container
        if not self._remove_container():
            log_error(f"Could not remove container {self.container_name}")
            return False

        # Start container with systemd support
        # Requires --privileged and cgroup mount for systemd to work
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    self.container_name,
                    "--privileged",
                    "--cgroupns=host",
                    "-v",
                    "/sys/fs/cgroup:/sys/fs/cgroup:rw",
                    "-v",
                    f"{self.installer_dir}:/installer:ro",
                    "-w",
                    "/installer",
                    self.image,
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            log_error(f"Failed to start container: {e}")
            return False

        # Wait for systemd to be ready
        log_info("Waiting for systemd to initialize...")
        for _i in range(30):  # Wait up to 30 seconds
            result = self.run("systemctl is-system-running 2>/dev/null || true")
            status = result.stdout.strip()
            if status in {"running", "degraded"}:
                break
            time.sleep(1)
        else:
            log_warning("systemd may not be fully ready, continuing anyway")

        log_success(f"Container {self.container_name} is ready with systemd")
        return True

    def teardown(self) -> None:
        """Stop and remove the container."""
        log_info(f"Stopping container: {self.container_name}")
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            check=False,
            capture_output=True,
        )

    def run(self, command: str, *, sudo: bool = False) -> CommandResult:
        """Run a command inside the container."""
        # sudo is a no-op in Docker (already root)
        docker_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash",
            "-c",
            command,
        ]

        log_debug(f"Docker exec: {command}")

        result = subprocess.run(
            docker_cmd,
            check=False,
            capture_output=True,
            text=True,
        )

        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def upload(self, local_path: Path, remote_path: str) -> bool:
        """Upload a file to the container."""
        try:
            subprocess.run(
                [
                    "docker",
                    "cp",
                    str(local_path),
                    f"{self.container_name}:{remote_path}",
                ],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """Upload a directory to the container."""
        if not self.upload(local_path, remote_path):
            return False
        # Fix permissions so all users can read
        self.run(f"chmod -R a+rX {remote_path}")
        return True

    def cleanup_cli(self) -> None:
        """Clean up CLI installation from container."""
        log_info("Cleaning up CLI installation...")
        self.run("rm -rf ~/.hop3-cli ~/.local/bin/hop3 ~/.local/bin/hop")
        log_success("CLI cleanup complete")

    def cleanup_server(self) -> None:
        """Clean up server installation from container."""
        log_info("Cleaning up server installation...")
        # Stop services first
        self.run("systemctl stop hop3-server uwsgi-hop3 2>/dev/null || true")
        self.run("rm -rf /home/hop3 /etc/hop3")
        self.run("userdel -r hop3 2>/dev/null || true")
        self.run(
            "rm -f /etc/systemd/system/hop3-server.service "
            "/etc/systemd/system/uwsgi-hop3.service"
        )
        self.run("systemctl daemon-reload")
        log_success("Server cleanup complete")

    def get_installer_path(self, installer_type: str) -> str:
        """Get path to installer in container (mounted volume)."""
        if installer_type == "cli":
            return "/installer/install-cli.py"
        return "/installer/install-server.py"
