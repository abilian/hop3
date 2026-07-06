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
import re
import subprocess
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3.config import APP_ROOT
from hop3.core.protocols import BuildArtifact, BuildContext
from hop3.lib import Abort, Diagnosis, abort_with_diagnosis, log
from hop3.lib.logging import server_log

if TYPE_CHECKING:
    from pathlib import Path

# Single generous build timeout. Per-app tier declarations are intentionally
# gone: guessing build durations in advance was error-prone and introduced
# two parallel timeout systems (build tier + test tier). Anything above 30
# minutes is a design smell — use a lighter packaging profile (docker-gen,
# nixpkgs-wrapper against a pre-built pkgs.X) rather than cranking this up.
BUILD_TIMEOUT_SECONDS = 30 * 60

# An exception class name, e.g. Redis::CannotConnectError, LoadError, NameError.
_BUILD_EXCEPTION_RE = re.compile(r"\b[A-Z][\w:]*(?:Error|Exception|Refused)\b.*")
# Fallback markers when no exception class is present (BuildKit / shell errors).
_BUILD_ERROR_MARKERS = (
    "rake aborted",
    "error:",
    "cannot ",
    "no such file",
    "failed to ",
    "not found",
    "fatal",
)


def _extract_build_error(output: str) -> str:
    """Best-effort one-line root cause from a build log.

    The real error is a needle in a haystack of backtrace + BuildKit noise.
    Prefer the first exception line (`Foo::BarError: …`), else the first strong
    error marker, else the last non-empty line. Trimmed to keep the summary one
    line; the full log lives in build.log.
    """
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    for ln in lines:
        m = _BUILD_EXCEPTION_RE.search(ln)
        if m:
            return m.group(0)[:300]
    for ln in lines:
        low = ln.lower()
        if any(mk in low for mk in _BUILD_ERROR_MARKERS):
            return ln[:300]
    return lines[-1][:300] if lines else "(no build output)"


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

        timeout_seconds = BUILD_TIMEOUT_SECONDS
        timeout_minutes = timeout_seconds // 60

        log(
            f"Running: docker build -t {image_tag} . (timeout={timeout_minutes}min)",
            level=2,
            fg="cyan",
        )

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
                timeout=timeout_seconds,
                env=env,
            )
            self._handle_build_success(result, image_tag, start_time)

        except FileNotFoundError:
            abort_with_diagnosis(
                Diagnosis(
                    component="Docker builder",
                    action="run docker command",
                    reason="the 'docker' binary was not found on the server",
                    hint=(
                        "Install Docker, or re-run the Hop3 installer with "
                        "'--with docker'"
                    ),
                    troubleshooting=[
                        "which docker",
                        "hop3-install server --with docker",
                    ],
                )
            )

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            self._save_build_log(
                "", f"Build timed out after {timeout_minutes} minutes", elapsed
            )
            abort_with_diagnosis(
                Diagnosis(
                    component="Docker builder",
                    action="build image",
                    reason=(f"build exceeded the {timeout_minutes}-minute timeout"),
                    hint=(
                        "Trim the Dockerfile (fewer RUN steps, leaner base "
                        "image), or switch this app to a lighter packaging "
                        "profile (docker-gen, nixpkgs-wrapper against a "
                        "pre-built pkgs.X) — a >30-min build is a design smell."
                    ),
                    troubleshooting=[
                        f"hop3 app logs --app {self.app_name} --build",
                        "Try 'docker build' locally to measure the build time",
                    ],
                )
            )

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
        """Handle a failed Docker build — report it ONCE.

        The full output is the one durable copy in build.log (retrievable via
        `hop3 app logs <app> --build`); the raised error carries only a concise
        root-cause line + a pointer, not the whole backtrace re-dumped at every
        layer (builder → deployer → RPC). Dumping it three times buried the one
        useful line in ~180 lines of repeated stack trace.
        """
        elapsed = time.time() - start_time
        # Docker buildx writes build logs to stderr, so check both.
        build_output = e.stderr or e.stdout or ""

        # The single full copy: build.log (path fixed to APP_ROOT above).
        self._save_build_log(e.stdout or "", e.stderr or "", elapsed, success=False)

        server_log.error(
            "Docker build failed",
            app_name=self.app_name,
            image_tag=image_tag,
            exit_code=e.returncode,
            duration_seconds=round(elapsed, 1),
            stderr=build_output[:1000],
        )

        if build_output:
            msg = (
                f"Docker build failed (exit {e.returncode}):\n"
                f"  {_extract_build_error(build_output)}\n"
                f"Full build log: hop3 app logs --app {self.app_name} --build"
            )
        else:
            msg = f"Docker build failed (exit {e.returncode}); no output captured"
        raise Abort(msg)

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
            # App log dir sits under APP_ROOT (= HOP3_ROOT/apps), NOT HOP3_ROOT
            # itself. Using HOP3_ROOT dropped build.log into /home/hop3/<app>/log/
            # — orphaned, since every reader (`hop3 app logs --build`, the test
            # diagnostic bundle) looks under /home/hop3/apps/<app>/log/. A failed
            # Docker build was captured but unretrievable. (Same fix the local
            # builder already carries.)
            app_log_dir = APP_ROOT / self.app_name / "log"
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
