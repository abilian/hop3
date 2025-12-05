# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Docker Compose deployment strategy for Hop3.

This deployer runs applications using Docker Compose, which allows for
complex multi-container deployments with networking, volumes, and scaling.
"""

from __future__ import annotations

import os
import subprocess
import traceback
from dataclasses import dataclass
from pathlib import Path

from hop3.config import HOP3_ROOT, HOP3_USER
from hop3.core.env import Env
from hop3.core.plugins import get_proxy_strategy
from hop3.core.protocols import (
    BuildArtifact,
    Deployer,
    DeploymentContext,
    DeploymentInfo,
)
from hop3.lib import Abort, get_free_port, log

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

        # Allocate a unique port for this app (like uWSGI deployments do)
        allocated_port = self._allocate_port()
        log(f"Allocated port {allocated_port} for '{self.app_name}'", level=2)

        # Build the docker compose command with project name for isolation
        # Using -p ensures each app has unique container names
        cmd = [
            "docker",
            "compose",
            "-p",
            self.app_name,  # Project name = app name for isolation
            "up",
            "-d",
            "--remove-orphans",
        ]

        # Add scaling if provided
        for service, count in deltas.items():
            cmd.extend(["--scale", f"{service}={count}"])

        # Set environment for compose file, including the allocated port
        compose_env = self._get_compose_env(allocated_port)

        self._run_compose_command(cmd, env=compose_env)

        log(f"App '{self.app_name}' deployed successfully.", level=2, fg="green")

        # Discover the actual port (should match allocated_port)
        port = self._discover_port(allocated_port)

        # Setup proxy if HOST_NAME is configured
        self._setup_proxy(port)

        return DeploymentInfo(
            protocol="http",
            address="127.0.0.1",
            port=port,
        )

    def _allocate_port(self) -> int:
        """Allocate a unique port for this app.

        If the app already has a port assigned (from previous deployment),
        try to reuse it. Otherwise, allocate a new free port.

        Returns:
            Allocated port number
        """
        # Check if app already has a port assigned
        if self.context.app and self.context.app.port:
            existing_port = self.context.app.port
            if existing_port > 0:
                log(f"Reusing existing port {existing_port}", level=2)
                return existing_port

        # Allocate a new free port
        port = get_free_port()
        log(f"Allocated new port {port}", level=2)
        return port

    def start(self) -> None:
        """Start the application."""
        log(f"Starting '{self.app_name}' with Docker Compose...", level=2, fg="blue")
        self.deploy()

    def stop(self) -> None:
        """Stop the application."""
        log(f"Stopping '{self.app_name}'...", level=2, fg="yellow")

        cmd = ["docker", "compose", "-p", self.app_name, "stop"]
        self._run_compose_command(cmd, check=False)

        log(f"App '{self.app_name}' stopped.", level=2, fg="green")

    def restart(self) -> None:
        """Restart the application."""
        log(f"Restarting '{self.app_name}'...", level=2, fg="blue")

        cmd = ["docker", "compose", "-p", self.app_name, "restart"]
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

        cmd = [
            "docker",
            "compose",
            "-p",
            self.app_name,
            "down",
            "--volumes",
            "--remove-orphans",
        ]
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

        # Get port from app or allocate new one
        port = self._allocate_port()

        cmd = ["docker", "compose", "-p", self.app_name, "up", "-d", "--no-recreate"]
        for service, count in deltas.items():
            cmd.extend(["--scale", f"{service}={count}"])

        env = self._get_compose_env(port)
        self._run_compose_command(cmd, env=env)

        log(f"App '{self.app_name}' scaled.", level=2, fg="green")

    def check_status(self) -> bool:
        """Check if the application is running.

        Returns:
            True if at least one container is running
        """
        try:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    self.app_name,
                    "ps",
                    "--format",
                    "{{.State}}",
                ],
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
                    "-p",
                    self.app_name,
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

    def _get_compose_env(self, port: int | None = None) -> dict[str, str]:
        """Get environment variables for Docker Compose.

        Args:
            port: Allocated host port for the app (passed to PORT env var)

        Returns:
            Dictionary of environment variables
        """
        # Start with a clean environment to avoid inheriting problematic vars
        # like PORT from the hop3-server itself
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "USER": os.environ.get("USER", ""),
        }

        # Add Docker-specific variables
        env["HOP3_IMAGE_TAG"] = self.artifact.location
        env["HOP3_APP_NAME"] = self.app_name

        # Set the PORT for docker-compose port mapping
        # This is used in docker-compose.yml: "127.0.0.1:${PORT:-8080}:8080"
        if port:
            env["PORT"] = str(port)

        # Pass through internal container port if available
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

    def _discover_port(self, expected_port: int | None = None) -> int:
        """Discover the HOST port the application is listening on.

        For Docker containers, the host port may differ from the container port
        due to port mapping (e.g., -p 5000:8080 maps host 5000 to container 8080).

        Args:
            expected_port: The port we allocated and expect to be used

        Returns:
            Host port number (defaults to expected_port or 8080 if not discoverable)
        """
        # Get internal container port from metadata (defaults to 8080)
        internal_port = 8080
        if "exposed_ports" in self.artifact.metadata:
            ports = self.artifact.metadata["exposed_ports"]
            if ports:
                internal_port = ports[0]

        # Try to get the actual HOST port from the running container
        # Use project name for proper isolation
        try:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    self.app_name,
                    "port",
                    "web",
                    str(internal_port),
                ],
                cwd=self.source_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Output format: 127.0.0.1:5000 or 0.0.0.0:32768
                port_str = result.stdout.strip().split(":")[-1]
                if port_str.isdigit():
                    discovered_port = int(port_str)
                    log(
                        f"Container port {internal_port} mapped to host port {discovered_port}",
                        level=2,
                    )
                    return discovered_port
        except Exception:
            pass

        # Fallback to expected port or internal port
        return expected_port or internal_port

    def _setup_proxy(self, port: int) -> None:
        """Setup proxy configuration if HOST_NAME is configured.

        Args:
            port: The port the container is accessible on
        """
        # Need an App instance to configure the proxy
        if not self.context.app:
            log(
                "Skipping proxy setup (no App in context)",
                level=2,
                fg="yellow",
            )
            return

        proxy_env = self._make_proxy_env(port)
        host_name = proxy_env.get("HOST_NAME", "_")

        if not host_name or host_name == "_":
            log(
                f"Skipping proxy setup for '{self.app_name}' (HOST_NAME not configured)",
                level=2,
                fg="yellow",
            )
            return

        log(
            f"Setting up proxy for '{self.app_name}' with HOST_NAME='{host_name}'",
            level=1,
            fg="blue",
        )

        try:
            workers = self._get_workers()
            proxy = get_proxy_strategy(self.context.app, proxy_env, workers)
            proxy.setup()
            log(
                f"✓ Proxy configured for '{self.app_name}'",
                level=1,
                fg="green",
            )
        except Exception as e:
            log(
                f"✗ Proxy setup failed for '{self.app_name}': {e}",
                level=1,
                fg="red",
            )
            traceback.print_exc()

    def _make_proxy_env(self, port: int) -> Env:
        """Create environment for proxy configuration.

        Follows the same pattern as StaticDeployer and AppLauncher.

        Args:
            port: The port the container is accessible on

        Returns:
            Env instance with proxy configuration
        """
        # Bootstrap environment
        env = Env({
            "APP": self.app_name,
            "HOME": str(HOP3_ROOT),
            "USER": HOP3_USER,
            "PATH": os.environ.get("PATH", ""),
            "PWD": str(self.source_path),
        })

        safe_defaults = {
            "NGINX_IPV4_ADDRESS": "0.0.0.0",
            "NGINX_IPV6_ADDRESS": "[::]",
            "BIND_ADDRESS": "127.0.0.1",
            "PORT": str(port),
            "HOST_NAME": "_",  # Default: catch-all, skips proxy setup
        }

        # Load environment variables shipped with repo (if any)
        env_file = self.source_path / "ENV"
        env.parse_settings(env_file)

        # Load environment variables from the ORM
        if self.context.app:
            env.update(self.context.app.get_runtime_env())

        # Handle IPv6
        if env.get_bool("DISABLE_IPV6"):
            safe_defaults.pop("NGINX_IPV6_ADDRESS", None)
            log("Proxy will NOT use IPv6", level=3)

        # Apply safe defaults for any unset values
        for k, v in safe_defaults.items():
            if k not in env:
                env[k] = v

        return env

    def _get_workers(self) -> dict[str, str]:
        """Get workers configuration for proxy.

        Docker apps have a single 'web' worker representing the container.
        The proxy will route traffic to BIND_ADDRESS:PORT.

        Returns:
            Workers dictionary for proxy configuration
        """
        return {"web": "docker-compose"}
