from __future__ import annotations

import subprocess

from hop3.core.protocols import BuildArtifact, BuildStrategy, DeploymentContext
from hop3.lib import Abort, log


class DockerBuildStrategy(BuildStrategy):
    """A build strategy that uses `docker build`."""

    name = "docker"

    def __init__(self, context: DeploymentContext):
        self.context = context

    def accept(self) -> bool:
        """Accepts if a Dockerfile is present in the source directory."""
        dockerfile_path = self.context.app_config.src_dir_path / "Dockerfile"
        return dockerfile_path.is_file()

    def build(self) -> BuildArtifact:
        """Runs `docker build` and returns a docker_image artifact."""
        app_name = self.context.app_name
        # A simple tagging scheme: hop3/<app-name>:latest
        image_tag = f"hop3/{app_name}:latest"
        src_path = self.context.app_config.src_dir_path

        log(f"Starting Docker build for image: {image_tag}", level=2, fg="blue")

        try:
            # Using subprocess.run for simplicity. A real implementation might
            # stream the output line by line using Popen.
            cmd = ["docker", "build", "-t", image_tag, "."]
            result = subprocess.run(
                cmd, cwd=src_path, check=True, capture_output=True, text=True
            )
            log(result.stdout, level=3)
        except FileNotFoundError:
            raise Abort(
                "Docker command not found. Is Docker installed and in your PATH?"
            )
        except subprocess.CalledProcessError as e:
            log(f"Docker build failed with exit code {e.returncode}:", fg="red")
            log(e.stderr, fg="red")
            raise Abort("Docker build failed.")

        log(f"Docker image '{image_tag}' built successfully.", fg="green")

        # We could inspect the image to find exposed ports, but for now
        # we'll rely on the docker-compose file to map them.
        return BuildArtifact(kind="docker_image", location=image_tag)
