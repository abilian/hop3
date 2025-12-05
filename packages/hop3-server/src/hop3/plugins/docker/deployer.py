# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Docker Compose deployment strategy for Hop3.

This deployer runs applications using Docker Compose, which allows for
complex multi-container deployments with networking, volumes, and scaling.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from hop3.core.protocols import (
    BuildArtifact,
    Deployer,
    DeploymentContext,
    DeploymentInfo,
)
from hop3.lib import Abort, log

# Default timeout for Docker commands (seconds)
DOCKER_COMMAND_TIMEOUT = 60


@dataclass(frozen=True)
class DockerComposeDeployer(Deployer):
    """Deployment strategy using Docker Compose.

    This deployer:
    1. Accepts docker-image artifacts from DockerBuilder
    2. Uses docker-compose.yml in the app source to orchestrate containers
    3. Manages lifecycle (start, stop, restart, scale)

    Requirements:
    - Docker and Docker Compose must be installed
    - App must have a docker-compose.yml file
    - The compose file should reference ${HOP3_IMAGE_TAG} for the app image
    """

    context: DeploymentContext
    artifact: BuildArtifact
    name: str = "docker-compose"

    @property
    def source_path(self) -> Path:
        """Get the source path from context."""
        return self.context.source_path

    @property
    def app_name(self) -> str:
        """Get the app name from context."""
        return self.context.app_name

    def accept(self) -> bool:
        """Check if this deployer can handle the artifact.

        Returns:
            True if artifact is a docker-image and compose file exists
        """
        if self.artifact.kind != "docker-image":
            return False

        # Check for docker-compose.yml or docker-compose.yaml
        compose_files = [
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
        ]
        return any((self.source_path / f).exists() for f in compose_files)

    def deploy(self, deltas: dict[str, int] | None = None) -> DeploymentInfo:
        """Deploy the application using Docker Compose.

        Args:
            deltas: Optional scaling deltas for services

        Returns:
            DeploymentInfo with connection details

        Raises:
            Abort: If deployment fails
        """
        deltas = deltas or {}

        log(f"Deploying '{self.app_name}' with Docker Compose...", level=2, fg="blue")

        # Build the docker compose command
        cmd = ["docker", "compose", "up", "-d", "--remove-orphans"]

        # Add scaling if provided
        for service, count in deltas.items():
            cmd.extend(["--scale", f"{service}={count}"])

        # Set environment for compose file
        env = self._get_compose_env()

        self._run_compose_command(cmd, env=env)

        log(f"App '{self.app_name}' deployed successfully.", level=2, fg="green")

        # Get the port from artifact metadata or discover it
        port = self._discover_port()

        return DeploymentInfo(
            protocol="http",
            address="127.0.0.1",
            port=port,
        )

    def start(self) -> None:
        """Start the application."""
        log(f"Starting '{self.app_name}' with Docker Compose...", level=2, fg="blue")
        self.deploy()

    def stop(self) -> None:
        """Stop the application."""
        log(f"Stopping '{self.app_name}'...", level=2, fg="yellow")

        cmd = ["docker", "compose", "stop"]
        self._run_compose_command(cmd, check=False)

        log(f"App '{self.app_name}' stopped.", level=2, fg="green")

    def restart(self) -> None:
        """Restart the application."""
        log(f"Restarting '{self.app_name}'...", level=2, fg="blue")

        cmd = ["docker", "compose", "restart"]
        try:
            self._run_compose_command(cmd)
            log(f"App '{self.app_name}' restarted.", level=2, fg="green")
        except Abort:
            # Fallback to stop/start
            log("Restart failed, falling back to stop/start...", level=2, fg="yellow")
            self.stop()
            self.start()

    def destroy(self) -> None:
        """Destroy the application and clean up resources."""
        log(f"Destroying '{self.app_name}'...", level=2, fg="yellow")

        cmd = ["docker", "compose", "down", "--volumes", "--remove-orphans"]
        self._run_compose_command(cmd, check=False)

        log(f"App '{self.app_name}' destroyed.", level=2, fg="green")

    def scale(self, deltas: dict[str, int] | None = None) -> None:
        """Scale services up or down.

        Args:
            deltas: Dictionary mapping service names to desired replica counts
        """
        deltas = deltas or {}
        if not deltas:
            log("No scaling deltas provided.", level=2, fg="yellow")
            return

        log(f"Scaling '{self.app_name}': {deltas}", level=2, fg="blue")

        cmd = ["docker", "compose", "up", "-d", "--no-recreate"]
        for service, count in deltas.items():
            cmd.extend(["--scale", f"{service}={count}"])

        env = self._get_compose_env()
        self._run_compose_command(cmd, env=env)

        log(f"App '{self.app_name}' scaled.", level=2, fg="green")

    def check_status(self) -> bool:
        """Check if the application is running.

        Returns:
            True if at least one container is running
        """
        try:
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "{{.State}}"],
                cwd=self.source_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=DOCKER_COMMAND_TIMEOUT,
            )

            if result.returncode != 0:
                return False

            states = result.stdout.strip().split("\n")
            return any("running" in state.lower() for state in states if state)

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    def get_status(self) -> dict:
        """Get detailed status of the deployment.

        Returns:
            Dictionary with running status and service details
        """
        services: dict[str, dict[str, str]] = {}
        status: dict[str, bool | dict[str, dict[str, str]]] = {
            "running": False,
            "services": services,
        }

        try:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "ps",
                    "--format",
                    "{{.Name}}\t{{.State}}\t{{.Status}}",
                ],
                cwd=self.source_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=DOCKER_COMMAND_TIMEOUT,
            )

            if result.returncode != 0 or not result.stdout.strip():
                return status

            for line in result.stdout.strip().split("\n"):
                if "\t" not in line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    name, state = parts[0], parts[1]
                    service_status = parts[2] if len(parts) > 2 else ""
                    services[name] = {
                        "state": state,
                        "status": service_status,
                    }
                    if "running" in state.lower():
                        status["running"] = True

        except Exception as e:
            log(f"Error getting status: {e}", level=3, fg="yellow")

        return status

    def _get_compose_env(self) -> dict[str, str]:
        """Get environment variables for Docker Compose.

        Returns:
            Dictionary of environment variables
        """
        import os

        env = os.environ.copy()
        env["HOP3_IMAGE_TAG"] = self.artifact.location
        env["HOP3_APP_NAME"] = self.app_name

        # Pass through exposed ports if available
        if "exposed_ports" in self.artifact.metadata:
            ports = self.artifact.metadata["exposed_ports"]
            if ports:
                env["HOP3_APP_PORT"] = str(ports[0])

        return env

    def _run_compose_command(
        self,
        cmd: list[str],
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a Docker Compose command.

        Args:
            cmd: Command and arguments
            env: Environment variables (optional)
            check: Whether to raise on non-zero exit

        Returns:
            CompletedProcess result

        Raises:
            Abort: If command fails and check=True
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=self.source_path,
                check=check,
                capture_output=True,
                text=True,
                env=env,
                timeout=DOCKER_COMMAND_TIMEOUT,
            )
            return result

        except FileNotFoundError:
            msg = "Docker Compose not found. Is Docker installed?"
            raise Abort(msg)

        except subprocess.TimeoutExpired:
            msg = f"Docker Compose command timed out: {' '.join(cmd)}"
            raise Abort(msg)

        except subprocess.CalledProcessError as e:
            log(f"Docker Compose failed: {e.stderr}", level=2, fg="red")
            msg = f"Docker Compose command failed: {' '.join(cmd)}"
            raise Abort(msg)

    def _discover_port(self) -> int:
        """Discover the port the application is listening on.

        Returns:
            Port number (defaults to 8080 if not discoverable)
        """
        # First check artifact metadata
        if "exposed_ports" in self.artifact.metadata:
            ports = self.artifact.metadata["exposed_ports"]
            if ports:
                return ports[0]

        # Try to get port from running container
        try:
            result = subprocess.run(
                ["docker", "compose", "port", "web", "8080"],
                cwd=self.source_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Output format: 0.0.0.0:32768
                port_str = result.stdout.strip().split(":")[-1]
                if port_str.isdigit():
                    return int(port_str)
        except Exception:
            pass

        # Default fallback
        return 8080
