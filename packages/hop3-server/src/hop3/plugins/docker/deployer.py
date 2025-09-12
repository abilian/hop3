# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import subprocess
import traceback

from hop3.core.protocols import (
    BuildArtifact,
    DeploymentContext,
    DeploymentInfo,
    DeploymentStrategy,
)
from hop3.lib import Abort, log


class DockerComposeDeploymentStrategy(DeploymentStrategy):
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
