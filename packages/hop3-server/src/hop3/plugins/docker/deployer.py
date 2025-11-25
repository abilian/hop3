# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import subprocess
import traceback

from hop3.core.protocols import (
    BuildArtifact,
    Deployer,
    DeploymentContext,
    DeploymentInfo,
)
from hop3.lib import Abort, log


class DockerComposeDeployer(Deployer):
    """A deployment strategy that uses `docker-compose up`."""

    name = "docker-compose"

    def __init__(self, context: DeploymentContext, artifact: BuildArtifact):
        self.context = context
        self.artifact = artifact

    def accept(self) -> bool:
        """Accepts if the artifact is a docker-image."""
        return self.artifact.kind == "docker-image"

    def deploy(self, deltas: dict | None = None) -> DeploymentInfo:
        """
        Runs `docker-compose up -d`. It uses an environment variable
        to pass the specific image tag to the compose file.
        """
        app_name = self.context.app_name
        src_path = self.context.source_path

        log(
            f"Deploying with Docker Compose for app '{app_name}'...", level=2, fg="blue"
        )

        # Prepare environment variables for the docker-compose command.
        # This allows the compose file to be generic.
        compose_env = {
            # **os.environ,  # Inherit environment (TODO: only the relevant parts)
            "HOP3_IMAGE_TAG": self.artifact.location,
            # Could also pass in a default port, e.g., "HOP3_PORT": "8080"
        }

        try:
            cmd = ["/usr/local/bin/docker", "compose", "up", "-d", "--remove-orphans"]
            # Add scaling logic if provided
            if deltas:
                for _service, _count_delta in deltas.items():
                    # This requires getting the current scale, let's assume `up` handles it for now.
                    # A more robust implementation would be needed for precise scaling.
                    log(
                        "Scaling not yet fully implemented for docker-compose, redeploying services...",
                        fg="yellow",
                    )

            subprocess.run(cmd, cwd=src_path, check=True, env=compose_env)
        except FileNotFoundError:
            traceback.print_exc()
            msg = (
                "'docker compose' command not found. Is it installed and in your PATH?"
            )
            raise Abort(msg)
        except subprocess.CalledProcessError as e:
            msg = f"Docker Compose deployment failed: {e}"
            raise Abort(msg)

        log(f"App '{app_name}' deployed successfully via Docker Compose.", fg="green")

        # This part is tricky. A real implementation would need to inspect the
        # docker-compose services to find the published host port.
        # For now, we return a placeholder.
        return DeploymentInfo(
            protocol="http", address="127.0.0.1", port=8080
        )  # Assume port 8080 for now

    def stop(self):
        """Runs `docker-compose down`."""
        log(
            f"Stopping Docker Compose services for '{self.context.app_name}'...",
            fg="yellow",
        )
        src_path = self.context.source_path
        subprocess.run(["docker", "compose", "down"], check=False, cwd=src_path)

    def start(self) -> None:
        """Start the app by deploying with no scaling changes."""
        log(
            f"Starting '{self.context.app_name}' with Docker Compose...",
            level=2,
            fg="blue",
        )
        self.deploy({})

    def restart(self) -> None:
        """Restart Docker Compose services."""
        log(f"Restarting '{self.context.app_name}'...", level=2, fg="blue")
        src_path = self.context.source_path
        try:
            subprocess.run(["docker", "compose", "restart"], check=True, cwd=src_path)
            log(
                f"App '{self.context.app_name}' restart triggered.", level=2, fg="green"
            )
        except subprocess.CalledProcessError as e:
            log(
                f"Docker Compose restart failed, falling back to stop/start: {e}",
                fg="yellow",
            )
            self.stop()
            self.start()

    def destroy(self) -> None:
        """Destruction is a superset of stop."""
        self.stop()

    def scale(self, deltas: dict[str, int] | None = None) -> None:
        """Scale Docker Compose services."""
        deltas = deltas or {}
        if not deltas:
            log("No scaling deltas provided", fg="yellow")
            return

        log(
            f"Scaling '{self.context.app_name}' with deltas: {deltas}",
            level=2,
            fg="blue",
        )
        src_path = self.context.source_path
        scale_args = []
        for service, count in deltas.items():
            scale_args.extend(["--scale", f"{service}={count}"])

        try:
            cmd = ["docker", "compose", "up", "-d", "--remove-orphans"] + scale_args
            subprocess.run(cmd, check=True, cwd=src_path)
            log(f"App '{self.context.app_name}' scaled successfully.", fg="green")
        except subprocess.CalledProcessError as e:
            msg = f"Docker Compose scaling failed: {e}"
            raise Abort(msg)

    def check_status(self) -> bool:
        """Check if Docker Compose services are actually running.

        Returns:
            True if containers are confirmed running, False otherwise.

        Uses `docker compose ps` to check the status of services.
        """
        src_path = self.context.source_path

        try:
            # Use docker compose ps with format to get service status
            # Format: {{.Name}}\t{{.State}}
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "{{.Name}}\t{{.State}}"],
                cwd=src_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                # docker compose ps failed - likely no compose file or docker not running
                return False

            # Parse output to check if any services are running
            lines = result.stdout.strip().split("\n")
            if not lines or lines[0] == "":
                # No services found
                return False

            # Check if at least one service is in "running" state
            for line in lines:
                if "\t" in line:
                    _name, state = line.split("\t", 1)
                    if "running" in state.lower():
                        return True

            # No running services found
            return False

        except subprocess.TimeoutExpired:
            log(
                f"Timeout checking status for '{self.context.app_name}'",
                fg="yellow",
            )
            return False
        except FileNotFoundError:
            # docker command not available
            log("Docker command not found", fg="red")
            return False
        except Exception as e:
            log(
                f"Error checking Docker Compose status for '{self.context.app_name}': {e}",
                fg="red",
            )
            return False

    def _parse_service_line(self, line: str) -> tuple[str, dict] | None:
        """Parse a single service status line.

        Args:
            line: Tab-separated line with format: Name\tState\tStatus

        Returns:
            Tuple of (service_name, service_info) or None if line is invalid
        """
        if "\t" not in line:
            return None

        parts = line.split("\t")
        if len(parts) < 2:
            return None

        name, state = parts[0], parts[1]
        service_status = parts[2] if len(parts) > 2 else ""
        service_info = {
            "state": state,
            "status": service_status,
        }
        return name, service_info

    def _parse_docker_compose_output(self, output: str) -> dict:
        """Parse docker compose ps output into service status dict.

        Args:
            output: Output from docker compose ps command

        Returns:
            Dict with 'services' and 'running' keys
        """
        services = {}
        any_running = False

        for line in output.strip().split("\n"):
            parsed = self._parse_service_line(line)
            if parsed:
                name, service_info = parsed
                services[name] = service_info
                if "running" in service_info["state"].lower():
                    any_running = True

        return {
            "services": services,
            "running": any_running,
        }

    def get_status(self) -> dict:
        """Get detailed status of Docker Compose services."""
        src_path = self.context.source_path
        status = {
            "running": False,
            "services": {},
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
                cwd=src_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                status = self._parse_docker_compose_output(result.stdout)

        except Exception as e:
            log(
                f"Error getting Docker Compose status for '{self.context.app_name}': {e}",
                fg="yellow",
            )

        return status
