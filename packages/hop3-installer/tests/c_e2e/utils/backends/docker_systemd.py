# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Docker backend with systemd support for full service testing.

CQS conventions in this module:

- **Queries** (read-only, ``_docker_available``, ``_image_exists``,
  ``_container_exists``, ``_container_running``) return ``bool`` and
  never raise under normal operation.
- **Commands** (mutating, ``setup``, ``teardown``, ``upload``,
  ``upload_dir``, cleanup helpers, private ``_build_image`` /
  ``_remove_container``) raise :class:`BackendError` with a
  descriptive message on failure. They NEVER return ``False`` — a
  silent ``False`` return forced callers to hunt through log lines
  to find out what went wrong. Commands that previously returned
  ``bool`` now return ``True`` on success, so the ``Backend`` ABC
  contract is preserved; removing the return value entirely would
  require touching every caller and sibling backend, which is out
  of scope for this change.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from hop3_installer.common import CommandResult

from ..common import log_debug, log_info, log_success
from .base import Backend, BackendError

# The systemd-enabled image name
SYSTEMD_IMAGE = "hop3-test-systemd:latest"
CONTAINER_NAME = "hop3-test-systemd"


class DockerSystemdBackend(Backend):
    """
    Backend for testing in Docker containers with systemd support.

    This backend runs tests inside Docker containers with full systemd
    support, enabling testing of services like nginx, postgresql, and
    hop3-server systemd units.

    Requires:
    - Docker with --privileged support
    - Pre-built hop3-test-systemd:latest image
    """

    name = "docker-systemd"
    supports_systemd = True

    def __init__(self, installer_dir: Path | None = None):
        """
        Initialize Docker systemd backend.

        Args:
            installer_dir: Path to installer directory (for mounting)
        """
        # parents[4] = the hop3-installer package root (…/backends/…/tests/../),
        # which holds docker/Dockerfile.systemd and is mounted into the container.
        self.installer_dir = installer_dir or Path(__file__).parents[4]
        self.container_name = CONTAINER_NAME
        self.image = SYSTEMD_IMAGE

    # -- Queries ----------------------------------------------------------

    def _docker_available(self) -> bool:
        """Check if Docker is available and responsive."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                check=False,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _image_exists(self) -> bool:
        """Check if the systemd image exists locally."""
        result = subprocess.run(
            ["docker", "images", "-q", self.image],
            check=False,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def _container_exists(self) -> bool:
        """Check if the container exists (any state)."""
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={self.container_name}", "-q"],
            check=False,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def _container_running(self) -> bool:
        """Check if the container is currently running."""
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={self.container_name}", "-q"],
            check=False,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    # -- Commands ---------------------------------------------------------

    def _build_image(self) -> None:
        """
        Build the systemd-enabled Docker image.

        Command, returns ``None`` on success.

        Raises:
            BackendError: If the Dockerfile is missing or the build
                command fails or times out.
        """
        dockerfile = self.installer_dir / "docker" / "Dockerfile.systemd"
        if not dockerfile.exists():
            msg = f"Dockerfile.systemd not found at {dockerfile}"
            raise BackendError(msg)

        log_info("Building hop3-test-systemd image...")
        try:
            subprocess.run(
                [
                    "docker",
                    "build",
                    "-f",
                    str(dockerfile),
                    "-t",
                    self.image,
                    str(dockerfile.parent),
                ],
                check=True,
                capture_output=True,
                timeout=600,  # 10 minutes for build
            )
        except subprocess.CalledProcessError as e:
            stderr = (
                (e.stderr or b"").decode(errors="replace")
                if isinstance(e.stderr, (bytes, bytearray))
                else (e.stderr or "")
            )
            msg = f"Failed to build image {self.image}: {stderr[:500]}"
            raise BackendError(msg) from e
        except subprocess.TimeoutExpired as e:
            msg = f"Image build timed out (600s) for {self.image}"
            raise BackendError(msg) from e

        log_success("Image built successfully")

    def _remove_container(self) -> None:
        """
        Remove the existing container, retrying up to 10 times.

        No-op if the container doesn't exist.

        Raises:
            BackendError: If the container still exists after 10
                attempts (docker is wedged).
        """
        if not self._container_exists():
            return

        log_debug(f"Removing existing container: {self.container_name}")
        for _attempt in range(10):
            subprocess.run(
                ["docker", "rm", "-f", self.container_name],
                check=False,
                capture_output=True,
            )
            time.sleep(1)
            if not self._container_exists():
                return

        msg = (
            f"Could not remove container {self.container_name} after 10 "
            "attempts — docker may be in a broken state"
        )
        raise BackendError(msg)

    def setup(self) -> bool:
        """
        Start a privileged container with systemd and wait for it
        to be ready.

        Returns:
            ``True`` on success (preserved for ABC compatibility — the
            return value is not meaningful, failure is signalled via
            exception).

        Raises:
            BackendError: If Docker is unavailable, the image can't be
                built, the container can't be removed/started, or
                systemd fails to come up within 30 seconds.
        """
        if not self._docker_available():
            msg = "Docker is not available or not running"
            raise BackendError(msg)

        if not self._image_exists():
            log_info(f"Image {self.image} not found, building...")
            self._build_image()

        log_info(f"Starting container: {self.container_name} (image: {self.image})")

        self._remove_container()

        # Start container with systemd support.
        # Requires --privileged and cgroup mount for systemd to work.
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    self.container_name,
                    "--privileged",
                    "--cgroupns=host",
                    "-v",
                    "/sys/fs/cgroup:/sys/fs/cgroup:rw",
                    "-v",
                    f"{self.installer_dir}:/installer:ro",
                    "-w",
                    "/installer",
                    self.image,
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            stderr = (
                (e.stderr or b"").decode(errors="replace")
                if isinstance(e.stderr, (bytes, bytearray))
                else (e.stderr or "")
            )
            msg = f"Failed to start container {self.container_name}: {stderr[:500]}"
            raise BackendError(msg) from e

        # Wait for systemd to be ready (up to 30s)
        log_info("Waiting for systemd to initialize...")
        for _i in range(30):
            result = self.run("systemctl is-system-running 2>/dev/null || true")
            status = result.stdout.strip()
            if status in {"running", "degraded"}:
                log_success(f"Container {self.container_name} is ready with systemd")
                return True
            time.sleep(1)

        # systemd didn't come up. The container is alive but unusable
        # for service tests — fail hard so the caller doesn't chase
        # mysterious downstream errors.
        msg = (
            f"systemd did not report 'running' or 'degraded' in container "
            f"{self.container_name} within 30s"
        )
        raise BackendError(msg)

    def teardown(self) -> None:
        """
        Stop and remove the container. Idempotent: does nothing
        if the container doesn't exist.
        """
        log_info(f"Stopping container: {self.container_name}")
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            check=False,
            capture_output=True,
        )

    def run(self, command: str, *, sudo: bool = False) -> CommandResult:
        """
        Run a command inside the container and return its result.

        This is a command-query hybrid: it mutates state (running a
        subprocess) but tests need the output. Non-zero exit codes
        are NOT raised here — the caller inspects
        :attr:`CommandResult.returncode` — because many tests
        intentionally assert on failure exit codes.
        """
        # sudo is a no-op in Docker (already root)
        docker_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash",
            "-c",
            command,
        ]

        log_debug(f"Docker exec: {command}")

        result = subprocess.run(
            docker_cmd,
            check=False,
            capture_output=True,
            text=True,
        )

        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def upload(self, local_path: Path, remote_path: str) -> bool:
        """
        Copy a file from the host into the container.

        Returns:
            ``True`` on success (ABC compatibility).

        Raises:
            BackendError: If ``docker cp`` fails.
        """
        try:
            subprocess.run(
                [
                    "docker",
                    "cp",
                    str(local_path),
                    f"{self.container_name}:{remote_path}",
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            stderr = (
                (e.stderr or b"").decode(errors="replace")
                if isinstance(e.stderr, (bytes, bytearray))
                else (e.stderr or "")
            )
            msg = (
                f"Failed to upload {local_path} to "
                f"{self.container_name}:{remote_path}: {stderr[:500]}"
            )
            raise BackendError(msg) from e
        return True

    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """
        Copy a directory tree into the container and fix perms so
        all users can read it.

        Returns:
            ``True`` on success (ABC compatibility).

        Raises:
            BackendError: If the underlying ``upload`` fails.
        """
        self.upload(local_path, remote_path)
        # Fix permissions so all users can read
        self.run(f"chmod -R a+rX {remote_path}")
        return True

    def cleanup_cli(self) -> None:
        """Remove the CLI installation artifacts from the container."""
        log_info("Cleaning up CLI installation...")
        self.run("rm -rf ~/.hop3-cli ~/.local/bin/hop3 ~/.local/bin/hop")
        log_success("CLI cleanup complete")

    def cleanup_server(self) -> None:
        """Remove the server installation artifacts from the container."""
        log_info("Cleaning up server installation...")
        # Stop services first
        self.run("systemctl stop hop3-server uwsgi-hop3 2>/dev/null || true")
        self.run("rm -rf /home/hop3 /etc/hop3")
        self.run("userdel -r hop3 2>/dev/null || true")
        self.run(
            "rm -f /etc/systemd/system/hop3-server.service "
            "/etc/systemd/system/uwsgi-hop3.service"
        )
        self.run("systemctl daemon-reload")
        log_success("Server cleanup complete")

    def get_installer_path(self, installer_type: str) -> str:
        """
        Return the path to the installer inside the container
        (mounted via the ``/installer`` volume).
        """
        if installer_type == "cli":
            return "/installer/install-cli.py"
        return "/installer/install-server.py"
