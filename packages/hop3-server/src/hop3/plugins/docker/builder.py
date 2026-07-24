# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Docker build strategy for Hop3.

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
_BUILD_EXCEPTION_RE = re.compile(
    # `Foo::BarError: …` / `SomeException: …`
    r"\b[A-Z][\w:]*(?:Error|Exception|Refused)\b.*"
    # …plus the Ruby `Errno::ENOENT: …` shape, which has no Error/Exception suffix.
    r"|\b[A-Z]\w*(?:::[A-Z]\w*)+:\s.*"
)
# Fallback markers when no exception class is present (BuildKit / shell errors).
# `fatal:` keeps its colon on purpose: a bare "fatal" also matches ordinary
# output that merely CONTAINS the word — Ruby's `configuring ext/-test-/fatal`
# (a directory name) was once reported as the root cause of an unrelated failure.
_BUILD_ERROR_MARKERS = (
    "rake aborted",
    "error:",
    "cannot ",
    "no such file",
    "failed to ",
    "not found",
    "fatal:",
    "fatal error",
    # How common toolchains announce a failure without an exception class:
    # ghost-cli/doctor-style checks ("… [failed]"), npm, apt ("E: …"), and the
    # usual permission/support refusals. Safe now that we only look at the
    # failing step's own output.
    "[failed]",
    "npm err!",
    "permission denied",
    "is not supported",
    "unable to locate",
)

# BuildKit tags every line with its step: `#12 124.5 <output>`, and announces the
# step that failed as `#12 ERROR: <message>`.
_BUILDKIT_STEP_ERROR_RE = re.compile(r"^#(\d+)\s+ERROR:?\s*(.*)")
_BUILDKIT_PREFIX_RE = re.compile(r"^#\d+\s+(?:\d+\.\d+\s+)?")
# When a RUN step's command exits non-zero, BuildKit's own ERROR line only echoes
# the command back — the real cause is in that step's output. But when a step
# fails without producing output (pulling a base image, resolving metadata), the
# ERROR line carries the ONLY message there is, e.g.
#   #2 ERROR: unexpected status from HEAD request to …/manifests/trixie-slim:
#            500 Internal Server Error
# So the ERROR line is a fallback, used when the step's own output says nothing.
_USELESS_STEP_ERROR = re.compile(r"did not complete successfully|process \"")

# A build can fail because the REGISTRY is having a bad day, not because anything
# is wrong with the app — e.g. Docker Hub answering the manifest HEAD request with
# a 500. Retrying fixes that; failing the deploy for it does not. Rate limiting
# (429 / "toomanyrequests") is deliberately NOT in here: Docker Hub's quota resets
# over hours, so retrying would just burn the remaining budget and still fail.
_TRANSIENT_REGISTRY_RE = re.compile(
    r"5\d\d\s+(?:internal server error|bad gateway|service unavailable|gateway time)"
    r"|tls handshake timeout"
    r"|i/o timeout"
    r"|connection reset by peer"
    r"|unexpected eof"
    r"|temporary failure in name resolution",
    re.IGNORECASE,
)
_REGISTRY_CONTEXT_RE = re.compile(
    r"failed to resolve source metadata|load metadata|failed to (?:copy|fetch|pull)"
    r"|registry-1\.docker\.io|docker\.io/",
    re.IGNORECASE,
)

_BUILD_ATTEMPTS = 3
_BUILD_RETRY_DELAYS = (5, 15, 0)  # before attempt 2, before attempt 3, unused


def unpinned_base_images(dockerfile: str) -> list[str]:
    """
    Base images referenced by tag rather than by digest.

    ``scratch`` needs no digest (it is empty by definition), and a ``FROM``
    naming an earlier build stage refers to something built in this same file,
    so neither is reported.
    """
    stages: set[str] = set()
    unpinned: list[str] = []
    for raw in dockerfile.splitlines():
        line = raw.strip()
        if not line.upper().startswith("FROM "):
            continue
        parts = line.split()
        image = parts[1]
        # `FROM x AS builder` declares a stage that later FROMs may reference
        if len(parts) >= 4 and parts[2].upper() == "AS":
            stages.add(parts[3])
        if image == "scratch" or image in stages or "@sha256:" in image:
            continue
        unpinned.append(image)
    return unpinned


class _TransientRegistryError(Exception):
    """An upstream registry blip that is worth retrying."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _is_transient_registry_error(output: str) -> bool:
    """
    Whether a build failure is an upstream registry blip rather than the app's.

    Both halves must hold — a transient-looking network/5xx symptom AND a
    registry context — AND both within the FAILING STEP's own output. The
    scoping is essential: "[internal] load metadata for docker.io/..." and the
    "FROM docker.io/..." line appear in EVERY build log, so an app's own RUN-step
    failure (e.g. a truncated ``curl | tar`` printing "Unexpected EOF in
    archive") would otherwise borrow that ambient registry context and be retried
    as an outage. A genuine base-image pull failure keeps its registry phrases
    inside the failing metadata/FROM step, so it still matches. With no numbered
    failing step (a bare solve-phase error) fall back to the whole log.
    """
    failing_output, message = _failing_step(output.splitlines())
    scope = (
        "\n".join([*failing_output, message]) if (failing_output or message) else output
    )
    return bool(
        _TRANSIENT_REGISTRY_RE.search(scope) and _REGISTRY_CONTEXT_RE.search(scope)
    )


def _failing_step(lines: list[str]) -> tuple[list[str], str]:
    """
    (output of the BuildKit step that failed, that step's ERROR message).

    Scoping extraction to the failing step is what stops an early, benign line
    from being reported as the root cause: a step-#7 line could out-rank the real
    step-#12 error simply by appearing first in the log.
    """
    step: str | None = None
    message = ""
    for ln in lines:
        m = _BUILDKIT_STEP_ERROR_RE.match(ln)
        if m:
            step, message = m.group(1), m.group(2).strip()
    if step is None:
        return [], ""
    prefix = f"#{step} "
    output = [
        _BUILDKIT_PREFIX_RE.sub("", ln)
        for ln in lines
        if ln.startswith(prefix) and not _BUILDKIT_STEP_ERROR_RE.match(ln)
    ]
    if _USELESS_STEP_ERROR.search(message):
        message = ""
    return output, message


def _extract_build_error(output: str) -> str:
    """
    Best-effort one-line root cause from a build log.

    The real error is a needle in a haystack of backtrace + BuildKit noise. Search
    only the failing step's own output (falling back to the whole log when the
    output isn't BuildKit-tagged), preferring an exception line, then a strong
    error marker, then BuildKit's own message for the step, then the last line.
    The full log lives in build.log.
    """
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    if not lines:
        return "(no build output)"

    step_output, step_message = _failing_step(lines)
    scoped = step_output or lines
    for ln in scoped:
        m = _BUILD_EXCEPTION_RE.search(ln)
        if m:
            return m.group(0)[:300]
    for ln in scoped:
        low = ln.lower()
        if any(mk in low for mk in _BUILD_ERROR_MARKERS):
            return ln[:300]
    # The step produced no diagnosable output of its own (a base-image pull or a
    # metadata resolve that failed). BuildKit's ERROR line is then the only real
    # message — without this, we'd report the step's NAME ("[internal] load
    # metadata for docker.io/library/debian:trixie-slim") as if it were the cause.
    if step_message:
        return step_message[:300]
    return scoped[-1][:300]


@dataclass(frozen=True)
class DockerBuilder:
    """
    Build strategy that uses `docker build` to create container images.

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
        """
        Check if this builder should handle the project.

        Returns:
            True if a Dockerfile exists in the source directory
        """
        dockerfile_path = self.source_path / "Dockerfile"
        return dockerfile_path.is_file()

    def build(self) -> BuildArtifact:
        """
        Build a Docker image from the Dockerfile.

        Returns:
            BuildArtifact with kind="docker-image" and the image tag as location

        Raises:
            Abort: If Docker is not installed, a base image is unpinned, or the
                build fails
        """
        self._check_base_images_pinned()

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

    def _check_base_images_pinned(self) -> None:
        """
        Refuse to build when a base image is not pinned by digest.

        ``FROM debian:trixie-slim`` resolves to whatever that tag points at on
        the day of the build, so the image is not reproducible and the supply
        chain is unverifiable. ``FROM debian:trixie-slim@sha256:...`` names
        exact bytes.
        """
        dockerfile = self.source_path / "Dockerfile"
        if not dockerfile.is_file():
            return
        unpinned = unpinned_base_images(dockerfile.read_text())
        if not unpinned:
            return
        listed = ", ".join(unpinned)
        msg = (
            f"{self.app_name}: Dockerfile base image(s) not pinned by digest "
            f"({listed}). A tag is mutable, so the build cannot be reproduced "
            f"or audited. Pin with `FROM image:tag@sha256:...` — resolve the "
            f"digest via `docker buildx imagetools inspect <image> "
            f"--format '{{{{.Manifest.Digest}}}}'`."
        )
        raise Abort(msg)

    def _generate_image_tag(self) -> str:
        """
        Generate a Docker image tag for this app.

        Returns:
            Image tag in format: hop3/<app-name>:latest
        """
        # Sanitize app name for Docker tag (lowercase, no special chars)
        safe_name = self.app_name.lower().replace("_", "-")
        return f"hop3/{safe_name}:latest"

    def _run_docker_build(self, image_tag: str) -> None:
        """
        Execute docker build command.

        A build that fails because the *registry* is having a bad day (a 5xx on
        the manifest request, a TLS/i-o timeout) is retried: that is an upstream
        outage, not a fault in the app, and failing the deploy for it is a
        robustness bug. Nothing is retried silently — each attempt is logged.

        Args:
            image_tag: The tag to apply to the built image

        Raises:
            Abort: If Docker is not found or build fails
        """
        for attempt in range(1, _BUILD_ATTEMPTS + 1):
            try:
                self._attempt_docker_build(image_tag, attempt)
                return
            except _TransientRegistryError as e:
                delay = _BUILD_RETRY_DELAYS[attempt - 1]
                log(
                    f"Docker registry error (attempt {attempt}/{_BUILD_ATTEMPTS}): "
                    f"{e.detail} — retrying in {delay}s",
                    level=0,
                    fg="yellow",
                )
                time.sleep(delay)

    def _attempt_docker_build(self, image_tag: str, attempt: int) -> None:
        """
        One `docker build` attempt.

        Raises ``_TransientRegistryError`` when the failure is an upstream
        registry blip AND retries remain; otherwise aborts as usual.
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
            combined = f"{e.stdout or ''}\n{e.stderr or ''}"
            if attempt < _BUILD_ATTEMPTS and _is_transient_registry_error(combined):
                raise _TransientRegistryError(_extract_build_error(combined)) from e
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
        """
        Handle a failed Docker build — report it ONCE.

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
        """
        Save build log to app's log directory.

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
        """
        Extract metadata from Dockerfile.

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
        """
        Parse EXPOSE directives from Dockerfile.

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
        """
        Parse a single EXPOSE line from Dockerfile.

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
