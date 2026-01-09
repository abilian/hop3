# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Docker Compose deployment strategy for Hop3.

This deployer runs applications using Docker Compose, which allows for
complex multi-container deployments with networking, volumes, and scaling.

By default, Hop3 generates a docker-compose.yml based on the Dockerfile.
Users can provide their own compose file for advanced use cases (multi-container,
custom networks, volumes, etc.).
"""

from __future__ import annotations

import os
import subprocess
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

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
from hop3.lib.logging import server_log

# Default timeout for Docker commands (seconds)
DOCKER_COMMAND_TIMEOUT = 60

# Compose file names to check (in order of preference)
COMPOSE_FILES = [
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
]

# Generated compose file name (used when no user-supplied file exists)
GENERATED_COMPOSE_FILE = ".hop3-compose.yml"


@dataclass(frozen=True)
class DockerComposeDeployer(Deployer):
    """Deployment strategy using Docker Compose.

    This deployer:
    1. Accepts docker-image artifacts from DockerBuilder
    2. Generates a docker-compose.yml if not provided by the user
    3. Uses user-supplied compose file for advanced use cases
    4. Manages lifecycle (start, stop, restart, scale)

    Requirements:
    - Docker and Docker Compose must be installed
    - A Dockerfile must exist (handled by DockerBuilder)

    The deployer will generate a simple compose file based on:
    - The Docker image tag from the build artifact
    - The exposed port from the Dockerfile (defaults to 8080)
    - Environment variables from hop3.toml or ENV file

    For advanced use cases (multi-container, volumes, networks), users
    can provide their own docker-compose.yml file.
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
            True if artifact is a docker-image (compose file is optional)
        """
        # Accept any docker-image artifact
        # We'll generate a compose file if one doesn't exist
        return self.artifact.kind == "docker-image"

    def _get_compose_file(self) -> Path:
        """Get the compose file to use.

        Returns user-supplied compose file if it exists,
        otherwise generates one.

        Returns:
            Path to the compose file
        """
        # Check for user-supplied compose file
        for filename in COMPOSE_FILES:
            compose_path = self.source_path / filename
            if compose_path.exists():
                log(f"Using user-supplied compose file: {filename}", level=2)
                return compose_path

        # Generate a compose file
        return self._generate_compose_file()

    def _generate_compose_file(self) -> Path:
        """Generate a docker-compose.yml for the application.

        Returns:
            Path to the generated compose file
        """
        # Get container port using centralized logic
        container_port = self._get_container_port()
        log(f"Using container port {container_port} for compose file", level=2)

        # Build environment section with app's env vars (2-space YAML indent)
        env_lines = [f"      - PORT={container_port}"]

        # Log what env vars we're reading from the app
        app_env_vars = []
        if self.context.app:
            app_env_vars = [
                (ev.name, ev.value[:50] if ev.value else "")
                for ev in self.context.app.env_vars
            ]
            server_log.info(
                "Reading env vars from app",
                app_name=self.app_name,
                app_env_vars_count=len(self.context.app.env_vars),
                app_env_vars=app_env_vars,
            )

        # Add all app environment variables (DATABASE_URL, REDIS_URL, etc.)
        # For Docker containers, replace localhost with host.docker.internal
        # so containers can connect to services running on the host
        if self.context.app:
            for env_var in self.context.app.env_vars:
                # Transform localhost to host.docker.internal for service URLs
                # This allows containers to reach PostgreSQL/Redis on the host
                value = env_var.value
                if env_var.name in {
                    "DATABASE_URL",
                    "REDIS_URL",
                    "PGHOST",
                    "REDIS_HOST",
                    "MYSQL_HOST",
                }:
                    value = value.replace("localhost", "host.docker.internal")
                    value = value.replace("127.0.0.1", "host.docker.internal")
                env_lines.append(f"      - {env_var.name}={value}")

        env_section = "\n".join(env_lines)

        # Log env vars being injected for debugging
        env_var_names = [line.split("=")[0].strip().lstrip("- ") for line in env_lines]
        server_log.info(
            "Generated compose env section",
            app_name=self.app_name,
            env_line_count=len(env_lines),
            env_var_names=env_var_names,
        )

        # Generate compose content
        # extra_hosts with host-gateway makes host.docker.internal work on Linux
        # (it's built-in on Docker Desktop for macOS/Windows)
        compose_content = f"""# Generated by Hop3 - do not edit manually
# For advanced use cases, create your own docker-compose.yml
services:
  web:
    image: ${{HOP3_IMAGE_TAG}}
    ports:
      # Bind to localhost only - traffic routes through Hop3 proxy
      - "127.0.0.1:${{PORT:-{container_port}}}:{container_port}"
    environment:
{env_section}
    extra_hosts:
      # Allow container to reach host services (PostgreSQL, Redis)
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
"""

        # Write to generated compose file
        compose_path = self.source_path / GENERATED_COMPOSE_FILE
        compose_path.write_text(compose_content)
        log(f"Generated compose file: {GENERATED_COMPOSE_FILE}", level=2)

        return compose_path

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

        # Get or generate the compose file
        compose_file = self._get_compose_file()

        # Allocate a unique port for this app (like uWSGI deployments do)
        allocated_port = self._allocate_port()
        log(f"Allocated port {allocated_port} for '{self.app_name}'", level=2)

        # Build the docker compose command with project name for isolation
        # Using -p ensures each app has unique container names
        # Using -f specifies the compose file (user-supplied or generated)
        cmd = [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "-p",
            self.app_name,  # Project name = app name for isolation
            "up",
            "-d",
            "--force-recreate",  # Ensure container is recreated with new env vars
            "--remove-orphans",
        ]

        # Add scaling if provided
        for service, count in deltas.items():
            cmd.extend(["--scale", f"{service}={count}"])

        # Set environment for compose file, including the allocated port
        compose_env = self._get_compose_env(allocated_port)

        self._run_compose_command(cmd, env=compose_env)

        log(f"App '{self.app_name}' deployed successfully.", level=2, fg="green")

        # Save the image tag to the app for restart operations
        if self.context.app and self.artifact.location:
            self.context.app.image_tag = self.artifact.location
            log(f"Saved image tag: {self.artifact.location}", level=3)

        # Discover the actual port (should match allocated_port)
        port = self._discover_port(allocated_port, compose_file)

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

    def _get_container_port(self) -> int:
        """Get the container port for this application.

        Priority:
        1. hop3.toml [docker] port
        2. Dockerfile EXPOSE
        3. Default 8080

        Returns:
            Container port number
        """
        # Check hop3.toml [docker] port first (highest priority)
        hop3_config = self.context.app_config.get("hop3_config", {})
        docker_config = hop3_config.get("docker", {})
        if docker_config.get("port"):
            return int(docker_config["port"])

        # Fall back to Dockerfile EXPOSE
        if "exposed_ports" in self.artifact.metadata:
            ports = self.artifact.metadata["exposed_ports"]
            if ports:
                return ports[0]

        # Default to 8080
        return 8080

    def _get_compose_cmd_base(self) -> list[str]:
        """Get base docker compose command with file and project args.

        Returns:
            Base command list with -f and -p arguments
        """
        compose_file = self._get_compose_file()
        return [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "-p",
            self.app_name,
        ]

    def start(self) -> None:
        """Start the application."""
        log(f"Starting '{self.app_name}' with Docker Compose...", level=2, fg="blue")
        self.deploy()

    def stop(self) -> None:
        """Stop the application."""
        log(f"Stopping '{self.app_name}'...", level=2, fg="yellow")

        cmd = self._get_compose_cmd_base() + ["stop"]
        self._run_compose_command(cmd, check=False)

        log(f"App '{self.app_name}' stopped.", level=2, fg="green")

    def restart(self) -> None:
        """Restart the application."""
        log(f"Restarting '{self.app_name}'...", level=2, fg="blue")

        cmd = self._get_compose_cmd_base() + ["restart"]
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

        cmd = self._get_compose_cmd_base() + [
            "down",
            "--volumes",
            "--remove-orphans",
        ]
        self._run_compose_command(cmd, check=False)

        # Clean up generated compose file if it exists
        generated_file = self.source_path / GENERATED_COMPOSE_FILE
        if generated_file.exists():
            generated_file.unlink()
            log(f"Removed generated compose file: {GENERATED_COMPOSE_FILE}", level=2)

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

        cmd = self._get_compose_cmd_base() + ["up", "-d", "--no-recreate"]
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
            cmd = self._get_compose_cmd_base() + ["ps", "--format", "{{.State}}"]

            # Get environment for docker compose (needed to resolve ${HOP3_IMAGE_TAG})
            env = self._get_status_check_env()

            result = subprocess.run(
                cmd,
                cwd=self.source_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=DOCKER_COMMAND_TIMEOUT,
                env=env,
            )

            if result.returncode != 0:
                return False

            states = result.stdout.strip().split("\n")
            return any("running" in state.lower() for state in states if state)

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    def _get_status_check_env(self) -> dict[str, str]:
        """Get minimal environment for status check commands.

        Returns environment variables needed for docker compose to parse
        the compose file, particularly for variable substitution like
        ${HOP3_IMAGE_TAG}.
        """
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
        }

        # Get image tag from app model if available, otherwise generate default
        if self.context.app and self.context.app.image_tag:
            env["HOP3_IMAGE_TAG"] = self.context.app.image_tag
        else:
            # Fallback to generated tag format
            safe_name = self.app_name.lower().replace("_", "-")
            env["HOP3_IMAGE_TAG"] = f"hop3/{safe_name}:latest"

        # Add PORT for compose file port mapping resolution
        if self.context.app and self.context.app.port:
            env["PORT"] = str(self.context.app.port)

        return env

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
            cmd = self._get_compose_cmd_base() + [
                "ps",
                "--format",
                "{{.Name}}\t{{.State}}\t{{.Status}}",
            ]

            # Get environment for docker compose (needed to resolve ${HOP3_IMAGE_TAG})
            env = self._get_status_check_env()

            result = subprocess.run(
                cmd,
                cwd=self.source_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=DOCKER_COMMAND_TIMEOUT,
                env=env,
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

        These variables are available for substitution in docker-compose.yml
        using ${VAR} syntax. For user-supplied compose files, this enables
        them to access DATABASE_URL, REDIS_URL, and other app env vars.

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

        # Pass through internal container port
        container_port = self._get_container_port()
        env["HOP3_APP_PORT"] = str(container_port)

        # Add all app environment variables (DATABASE_URL, REDIS_URL, etc.)
        # This allows user compose files to use ${DATABASE_URL} syntax
        if self.context.app:
            for env_var in self.context.app.env_vars:
                env[env_var.name] = env_var.value

        return env

    def _run_compose_command(
        self,
        cmd: list[str],
        env: dict[str, str] | None = None,
        *,
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
        # Log the command being run at verbose level
        cmd_str = " ".join(cmd)
        log(f"Running: {cmd_str}", level=2, fg="cyan")

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

            # Log output at verbose level for debugging
            self._log_output(result.stdout, level=2, fg="cyan")
            self._log_output(result.stderr, level=2, fg="yellow")

            return result

        except FileNotFoundError:
            msg = "Docker Compose not found. Is Docker installed?"
            raise Abort(msg)

        except subprocess.TimeoutExpired:
            msg = f"Docker Compose command timed out: {cmd_str}"
            raise Abort(msg)

        except subprocess.CalledProcessError as e:
            self._handle_compose_error(e, cmd_str)

    def _log_output(
        self, output: str | None, level: int = 2, fg: str = "", prefix: str = "  "
    ) -> None:
        """Log multiline output line by line."""
        if not output:
            return
        for line in output.strip().split("\n"):
            if line.strip():
                log(f"{prefix}{line}", level=level, fg=fg)

    def _handle_compose_error(
        self, e: subprocess.CalledProcessError, cmd_str: str
    ) -> NoReturn:
        """Handle Docker Compose command error."""
        # Log detailed error for debugging
        log(
            f"Docker Compose failed with exit code {e.returncode}",
            level=1,
            fg="red",
        )
        stderr_msg = e.stderr.strip() if e.stderr else "No error details"
        stdout_msg = e.stdout.strip() if e.stdout else ""

        # Show full output for debugging
        if e.stdout:
            log("Command output:", level=1, fg="yellow")
            self._log_output(stdout_msg, level=1, prefix="  ")
        if e.stderr:
            log("Error output:", level=1, fg="red")
            self._log_output(stderr_msg, level=1, fg="red", prefix="  ")

        # Log to server_log for persistent debugging
        server_log.error(
            "Docker Compose command failed",
            app_name=self.app_name,
            command=cmd_str,
            exit_code=e.returncode,
            stderr=stderr_msg[:500],  # Truncate for logging
            stdout=stdout_msg[:200] if stdout_msg else "",
        )
        # Include stderr in the abort message for visibility
        msg = f"Docker Compose command failed: {cmd_str}\n  Error: {stderr_msg}"
        raise Abort(msg)

    def _discover_port(
        self, expected_port: int | None = None, compose_file: Path | None = None
    ) -> int:
        """Discover the HOST port the application is listening on.

        For Docker containers, the host port may differ from the container port
        due to port mapping (e.g., -p 5000:8080 maps host 5000 to container 8080).

        Args:
            expected_port: The port we allocated and expect to be used
            compose_file: Path to the compose file (optional)

        Returns:
            Host port number (defaults to expected_port or 8080 if not discoverable)
        """
        # Get internal container port using same priority as _generate_compose_file
        internal_port = self._get_container_port()

        # Try to get the actual HOST port from the running container
        # Use project name for proper isolation
        try:
            # Build command with compose file if provided
            if compose_file:
                cmd = [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    self.app_name,
                    "port",
                    "web",
                    str(internal_port),
                ]
            else:
                cmd = [
                    "docker",
                    "compose",
                    "-p",
                    self.app_name,
                    "port",
                    "web",
                    str(internal_port),
                ]

            result = subprocess.run(
                cmd,
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
