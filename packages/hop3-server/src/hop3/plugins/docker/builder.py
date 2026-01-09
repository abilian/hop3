# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Docker build strategy for Hop3.

This builder creates Docker images from applications that have a Dockerfile.
It integrates with the Hop3 build pipeline and produces artifacts that can
be deployed using DockerComposeDeployer.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from hop3.config import HOP3_ROOT
from hop3.core.protocols import BuildArtifact, BuildContext
from hop3.lib import Abort, log
from hop3.lib.logging import server_log


@dataclass(frozen=True)
class DockerBuilder:
    """Build strategy that uses `docker build` to create container images.

    This builder:
    1. Detects projects with a Dockerfile
    2. Runs `docker build` to create an image
    3. Returns a BuildArtifact with kind="docker-image"

    The resulting artifact can be deployed using DockerComposeDeployer.
    """

    context: BuildContext
    name: str = "docker"

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
        start_time = time.time()

        log(f"Running: docker build -t {image_tag} .", level=2, fg="cyan")

        # Enable BuildKit for modern Dockerfile features (COPY --chmod, etc.)
        # BuildKit is required for many modern Dockerfiles
        env = os.environ.copy()
        env["DOCKER_BUILDKIT"] = "1"

        try:
            result = subprocess.run(
                cmd,
                cwd=self.source_path,
                check=True,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for builds
                env=env,
            )
            self._handle_build_success(result, image_tag, start_time)

        except FileNotFoundError:
            msg = "Docker command not found. Is Docker installed and in your PATH?"
            raise Abort(msg)

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            self._save_build_log("", "Build timed out after 10 minutes", elapsed)
            msg = "Docker build timed out after 10 minutes."
            raise Abort(msg)

        except subprocess.CalledProcessError as e:
            self._handle_build_failure(e, image_tag, start_time)

    def _handle_build_success(
        self, result: subprocess.CompletedProcess, image_tag: str, start_time: float
    ) -> None:
        """Handle successful Docker build."""
        elapsed = time.time() - start_time

        # Log build output at verbose level (visible with -v flag)
        self._log_output(result.stdout, level=2, fg="cyan")

        # Save build logs to file for later retrieval
        self._save_build_log(result.stdout, result.stderr, elapsed)

        # Log summary at normal level
        log(f"Docker build completed in {elapsed:.1f}s", level=1, fg="green")

        # Log to server log for persistent debugging
        server_log.info(
            "Docker build completed",
            app_name=self.app_name,
            image_tag=image_tag,
            duration_seconds=round(elapsed, 1),
        )

    def _handle_build_failure(
        self, e: subprocess.CalledProcessError, image_tag: str, start_time: float
    ) -> None:
        """Handle failed Docker build."""
        elapsed = time.time() - start_time

        # Log error at normal level (always visible)
        log(f"Docker build failed with exit code {e.returncode}:", level=0, fg="red")

        # Docker buildx outputs build logs to stderr, so check both
        build_output = e.stderr or e.stdout or ""

        # Show full build output for debugging (level=1 = normal, always visible)
        if build_output:
            log("Build output:", level=1, fg="yellow")
            self._log_output(build_output, level=1, prefix="  ")

        # Save build logs for later retrieval
        self._save_build_log(e.stdout or "", e.stderr or "", elapsed, success=False)

        # Log to server log (truncated for structured logging)
        server_log.error(
            "Docker build failed",
            app_name=self.app_name,
            image_tag=image_tag,
            exit_code=e.returncode,
            duration_seconds=round(elapsed, 1),
            stderr=build_output[:1000] if build_output else "",
        )

        # Extract the last meaningful error line for the summary message
        error_summary = self._extract_error_summary(build_output)
        msg = f"Docker build failed: {error_summary}"
        raise Abort(msg)

    def _extract_error_summary(self, output: str) -> str:
        """Extract a meaningful error summary from Docker build output.

        Args:
            output: Full build output

        Returns:
            A concise error summary (last non-empty line or truncated output)
        """
        if not output:
            return "unknown error"

        # Docker buildx format: look for ERROR lines or the last meaningful line
        lines = [line.strip() for line in output.strip().split("\n") if line.strip()]
        if not lines:
            return "unknown error"

        # Look for lines containing "ERROR" or "error:"
        for line in reversed(lines):
            if "ERROR" in line.upper() or "error:" in line.lower():
                # Return the error line (up to 500 chars)
                return line[:500] if len(line) > 500 else line

        # Fall back to last line
        last_line = lines[-1]
        return last_line[:500] if len(last_line) > 500 else last_line

    def _log_output(
        self, output: str, level: int = 2, fg: str = "", prefix: str = ""
    ) -> None:
        """Log multiline output line by line."""
        if not output:
            return
        for line in output.strip().split("\n"):
            if line.strip():
                log(f"{prefix}{line}", level=level, fg=fg)

    def _save_build_log(
        self, stdout: str, stderr: str, duration: float, *, success: bool = True
    ) -> None:
        """Save build log to app's log directory.

        Args:
            stdout: Build stdout output
            stderr: Build stderr output
            duration: Build duration in seconds
            success: Whether build succeeded
        """
        try:
            # Determine log directory - use app path if available
            app_log_dir = HOP3_ROOT / self.app_name / "log"
            app_log_dir.mkdir(parents=True, exist_ok=True)

            build_log_path = app_log_dir / "build.log"

            # Format log content
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            status = "SUCCESS" if success else "FAILED"
            content = f"""=== Docker Build Log ===
Timestamp: {timestamp}
App: {self.app_name}
Status: {status}
Duration: {duration:.1f}s

=== STDOUT ===
{stdout}

=== STDERR ===
{stderr}
"""
            build_log_path.write_text(content)
            log(f"Build log saved to: {build_log_path}", level=2)

        except Exception as e:
            # Don't fail the build if log saving fails
            server_log.warning(
                "Failed to save build log",
                app_name=self.app_name,
                error=str(e),
            )

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
