# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Docker backend for testing in containers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hop3_installer.testing.common import (
    CommandResult,
    log_debug,
    log_error,
    log_info,
    log_success,
)

from .base import Backend

# Docker images for each distro
DOCKER_IMAGES = {
    "ubuntu": "ubuntu:24.04",
    "debian": "debian:12",
    "fedora": "fedora:40",
}

CONTAINER_PREFIX = "hop3-test"


class DockerBackend(Backend):
    """Backend for testing in Docker containers.

    This backend runs tests inside Docker containers, providing
    fast iteration and isolated testing without needing a remote server.

    Note: Server installer tests are limited (no systemd in containers).
    """

    name = "docker"
    supports_systemd = False  # No systemd in standard Docker containers

    def __init__(self, distro: str = "ubuntu", installer_dir: Path | None = None):
        """Initialize Docker backend.

        Args:
            distro: Distribution to test on (ubuntu, debian, fedora)
            installer_dir: Path to installer directory (for mounting)
        """
        self.distro = distro
        self.installer_dir = installer_dir or Path(__file__).parent.parent.parent
        self.container_name = f"{CONTAINER_PREFIX}-{distro}"
        self.image = DOCKER_IMAGES.get(distro, DOCKER_IMAGES["ubuntu"])

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

    def setup(self) -> bool:
        """Start Docker container for testing."""
        if not self._docker_available():
            log_error("Docker is not available or not running")
            return False

        log_info(f"Starting container: {self.container_name} (image: {self.image})")

        # Remove existing container if any
        if self._container_exists():
            log_debug(f"Removing existing container: {self.container_name}")
            subprocess.run(
                ["docker", "rm", "-f", self.container_name],
                check=False,
                capture_output=True,
            )

        # Start container with installer directory mounted (just sleep, no package install yet)
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    self.container_name,
                    "-v",
                    f"{self.installer_dir}:/installer:ro",
                    "-w",
                    "/installer",
                    self.image,
                    "sleep",
                    "infinity",
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            log_error(f"Failed to start container: {e}")
            return False

        # Install packages synchronously (not in background)
        log_info("Waiting for package installation...")
        if self.distro in {"ubuntu", "debian"}:
            install_cmd = (
                "apt-get update && apt-get install -y python3 python3-venv git curl"
            )
        else:  # fedora
            install_cmd = "dnf install -y python3 python3-pip git curl"

        try:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    self.container_name,
                    "bash",
                    "-c",
                    install_cmd,
                ],
                check=True,
                capture_output=True,
                timeout=300,  # 5 minutes for package installation
            )
        except subprocess.CalledProcessError as e:
            log_error(
                f"Package installation failed: {e.stderr[:200] if e.stderr else ''}"
            )
            return False
        except subprocess.TimeoutExpired:
            log_error("Package installation timed out")
            return False

        log_success(f"Container {self.container_name} is ready")
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
        # docker cp works the same for directories
        return self.upload(local_path, remote_path)

    def cleanup_cli(self) -> None:
        """Clean up CLI installation from container."""
        log_info("Cleaning up CLI installation...")
        self.run("rm -rf ~/.hop3-cli ~/.local/bin/hop3 ~/.local/bin/hop")
        log_success("CLI cleanup complete")

    def cleanup_server(self) -> None:
        """Clean up server installation from container."""
        log_info("Cleaning up server installation...")
        self.run("rm -rf /home/hop3 /etc/hop3")
        self.run("userdel -r hop3 2>/dev/null || true")
        log_success("Server cleanup complete")

    def get_installer_path(self, installer_type: str) -> str:
        """Get path to installer in container (mounted volume)."""
        if installer_type == "cli":
            return "/installer/install-cli.py"
        return "/installer/install-server.py"
