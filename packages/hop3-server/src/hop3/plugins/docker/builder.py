# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Docker build strategy for Hop3.

This builder creates Docker images from applications that have a Dockerfile.
It integrates with the Hop3 build pipeline and produces artifacts that can
be deployed using DockerComposeDeployer.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from hop3.core.protocols import BuildArtifact, BuildContext, DeploymentContext
from hop3.lib import Abort, log

if TYPE_CHECKING:
    from pathlib import Path


class DockerBuilder:
    """Build strategy that uses `docker build` to create container images.

    This builder:
    1. Detects projects with a Dockerfile
    2. Runs `docker build` to create an image
    3. Returns a BuildArtifact with kind="docker-image"

    The resulting artifact can be deployed using DockerComposeDeployer.
    """

    name = "docker"

    def __init__(self, context: BuildContext | DeploymentContext) -> None:
        """Initialize DockerBuilder with build context.

        Args:
            context: Build or deployment context containing app information
        """
        self.context = context

    @property
    def source_path(self) -> Path:
        """Get the source path from context."""
        return self.context.source_path

    @property
    def app_name(self) -> str:
        """Get the app name from context."""
        return self.context.app_name

    def accept(self) -> bool:
        """Check if this builder should handle the project.

        Returns:
            True if a Dockerfile exists in the source directory
        """
        dockerfile_path = self.source_path / "Dockerfile"
        return dockerfile_path.is_file()

    def build(self) -> BuildArtifact:
        """Build a Docker image from the Dockerfile.

        Returns:
            BuildArtifact with kind="docker-image" and the image tag as location

        Raises:
            Abort: If Docker is not installed or build fails
        """
        image_tag = self._generate_image_tag()

        log(f"Building Docker image: {image_tag}", level=2, fg="blue")

        self._run_docker_build(image_tag)

        log(f"Docker image '{image_tag}' built successfully.", level=2, fg="green")

        # Extract metadata from Dockerfile if possible
        metadata = self._extract_metadata()

        return BuildArtifact(
            kind="docker-image",
            location=image_tag,
            metadata=metadata,
        )

    def _generate_image_tag(self) -> str:
        """Generate a Docker image tag for this app.

        Returns:
            Image tag in format: hop3/<app-name>:latest
        """
        # Sanitize app name for Docker tag (lowercase, no special chars)
        safe_name = self.app_name.lower().replace("_", "-")
        return f"hop3/{safe_name}:latest"

    def _run_docker_build(self, image_tag: str) -> None:
        """Execute docker build command.

        Args:
            image_tag: The tag to apply to the built image

        Raises:
            Abort: If Docker is not found or build fails
        """
        cmd = ["docker", "build", "-t", image_tag, "."]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.source_path,
                check=True,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for builds
            )
            # Log build output at debug level
            if result.stdout:
                log(result.stdout, level=4)

        except FileNotFoundError:
            msg = "Docker command not found. Is Docker installed and in your PATH?"
            raise Abort(msg)

        except subprocess.TimeoutExpired:
            msg = "Docker build timed out after 10 minutes."
            raise Abort(msg)

        except subprocess.CalledProcessError as e:
            log(f"Docker build failed with exit code {e.returncode}:", level=1, fg="red")
            if e.stderr:
                log(e.stderr, level=1, fg="red")
            msg = f"Docker build failed: {e.stderr[:200] if e.stderr else 'unknown error'}"
            raise Abort(msg)

    def _extract_metadata(self) -> dict:
        """Extract metadata from Dockerfile.

        Returns:
            Dictionary with metadata like exposed ports
        """
        metadata: dict[str, str | list[int]] = {
            "app_name": self.app_name,
            "builder": "docker",
        }

        exposed_ports = self._parse_exposed_ports()
        if exposed_ports:
            metadata["exposed_ports"] = exposed_ports

        return metadata

    def _parse_exposed_ports(self) -> list[int]:
        """Parse EXPOSE directives from Dockerfile.

        Returns:
            List of exposed port numbers, empty if none found or on error
        """
        dockerfile_path = self.source_path / "Dockerfile"
        if not dockerfile_path.exists():
            return []

        try:
            content = dockerfile_path.read_text()
        except Exception:
            return []  # Metadata extraction is best-effort

        ports = []
        for line in content.splitlines():
            ports.extend(self._parse_expose_line(line))
        return ports

    def _parse_expose_line(self, line: str) -> list[int]:
        """Parse a single EXPOSE line from Dockerfile.

        Args:
            line: A line from the Dockerfile

        Returns:
            List of port numbers found on this line
        """
        line = line.strip()
        if not line.upper().startswith("EXPOSE"):
            return []

        ports = []
        # Parse: EXPOSE 8080 or EXPOSE 8080/tcp or EXPOSE 80 443
        for part in line.split()[1:]:
            port_str = part.split("/")[0]
            if port_str.isdigit():
                ports.append(int(port_str))
        return ports
