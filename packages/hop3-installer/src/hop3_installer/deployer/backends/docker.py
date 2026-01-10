# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Docker deployment backend for local containers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from .base import CommandResult, DeployBackend

if TYPE_CHECKING:
    from hop3_installer.deployer.config import DeployConfig


class DockerDeployBackend(DeployBackend):
    """Backend for deploying to local Docker containers.

    This backend creates a Docker container with systemd support
    for realistic testing of Hop3 server installation.
    """

    name = "docker"

    def __init__(self, config: DeployConfig):
        super().__init__(config)
        self.container_name = config.docker_container
        self.image = config.docker_image

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

    def setup(self) -> bool:
        """Start Docker container for deployment."""
        if not self._docker_available():
            print("  ✗ Docker is not available")
            return False

        # Always remove existing container first
        self._remove_container()

        # Start container with systemd
        # Use a privileged container to support systemd
        privileged_result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                self.container_name,
                "--privileged",
                "-v",
                "/sys/fs/cgroup:/sys/fs/cgroup:rw",
                "-v",
                f"{self.config.project_root}:/hop3:ro",
                "-p",
                "8000:8000",
                "-p",
                "8080:80",
                "-p",
                "8443:443",
                "--cgroupns=host",
                self.image,
                "/sbin/init",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if privileged_result.returncode != 0:
            # Remove failed container before retry
            self._remove_container()

            # Try without privileged mode (limited functionality)
            print("  → Privileged mode failed, trying basic mode...")
            basic_result = subprocess.run(
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

            if basic_result.returncode != 0:
                print("  ✗ Failed to start container")
                if basic_result.stderr:
                    print(f"  Error: {basic_result.stderr.strip()}")
                return False

        # Wait for container to be ready
        import time

        for _ in range(30):
            if self._container_running():
                break
            time.sleep(0.5)
        else:
            print("  ✗ Container failed to start within timeout")
            return False

        # Install base packages with streaming output
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
