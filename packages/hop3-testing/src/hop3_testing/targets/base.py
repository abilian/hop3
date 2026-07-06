# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Base class for deployment targets."""

from __future__ import annotations

import contextlib
import subprocess
import tarfile
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import httpx

from hop3_testing.exceptions import DeploymentError, TargetOutOfDiskError

from .constants import (
    E2E_TEST_SECRET_KEY,
    create_test_token,
    hermetic_cli_cwd,
    hermetic_cli_env,
)


@dataclass
class CommandResult:
    """Result of a command execution."""

    success: bool
    stdout: str
    stderr: str
    returncode: int
    duration: float = 0.0


@dataclass
class DeployResult:
    """Result of deploying an application."""

    success: bool
    app_name: str
    app_url: str | None = None
    logs: str = ""
    duration: float = 0.0
    error: str | None = None


@dataclass
class HttpResponse:
    """HTTP response from target."""

    status: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)
    duration: float = 0.0


@dataclass
class TargetInfo:
    """Information about a deployment target."""

    ssh_host: str
    ssh_port: int
    ssh_user: str = "root"
    ssh_key: str | None = None
    ssh_password: str | None = None
    http_base: str = ""
    api_url: str = ""
    # The server's JWT signing key, so the harness can mint tokens the server
    # accepts (real auth, no HOP3_UNSAFE bypass). None → the E2E default key,
    # correct for a server the harness started with that key (Docker).
    secret_key: str | None = None
    metadata: dict[str, Any] | None = None


class DeploymentTarget(ABC):
    """Abstract base class for deployment targets.

    A deployment target represents a Hop3 server where applications can be
    deployed and tested. This could be a Docker container, a VM, or a remote server.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize the deployment target.

        Args:
            config: Configuration dictionary for the target
        """
        self.config = config or {}
        self._info: TargetInfo | None = None

    @abstractmethod
    def start(self) -> TargetInfo:
        """Start the deployment target.

        Returns:
            TargetInfo with connection details
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop and cleanup the deployment target."""

    @property
    def info(self) -> TargetInfo:
        """Get target information.

        Returns:
            TargetInfo with connection details

        Raises:
            RuntimeError: If target hasn't been started yet
        """
        if self._info is None:
            msg = "Target not started yet. Call start() first."
            raise RuntimeError(msg)
        return self._info

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Execute a command on the target.

        Args:
            cmd: Command to execute (string or list)

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        msg = "exec_run not implemented for this target"
        raise NotImplementedError(msg)

    def upload_file(self, local_path: Path | str, remote_path: str) -> None:
        """Copy a single local file onto the target.

        Used by the on-server tutorial runner to place a tutorial markdown file
        on the box before invoking validoc there. Targets that can't accept an
        upload (or don't need to) leave this unimplemented.

        Args:
            local_path: Path to the local file to upload.
            remote_path: Absolute destination path on the target.
        """
        msg = "upload_file not implemented for this target"
        raise NotImplementedError(msg)

    def run_command(self, *args: str, timeout: int = 300) -> CommandResult:
        """Run a hop3 command on the target.

        Args:
            *args: Command and arguments (e.g., "backup", "create", "my-app")
            timeout: Command timeout in seconds

        Returns:
            CommandResult with success status and output
        """
        target_info = self.info
        start_time = time.time()

        # Hermetic: strip ambient HOP3_* steering vars (see hermetic_cli_env) so
        # the launch environment can't redirect this hop3 call; explicit target
        # URL + token are set below.
        env = hermetic_cli_env()
        # Prefer direct HTTP API URL when available (Docker without SSH port mapping)
        # Fall back to SSH tunnel for remote targets
        if target_info.api_url:
            env["HOP3_API_URL"] = target_info.api_url
            # Direct HTTP authenticates with a real JWT signed with the key the
            # server validates with (no HOP3_UNSAFE bypass). See
            # apps.deployment.DeploymentSession._build_cli_env for the rationale.
            env["HOP3_API_TOKEN"] = create_test_token(
                secret_key=target_info.secret_key or E2E_TEST_SECRET_KEY
            )
        else:
            # SSH tunnel provides implicit authentication via SSH keys
            env["HOP3_API_URL"] = f"ssh://{target_info.ssh_host}:{target_info.ssh_port}"
            env["HOP3_SSH_KEY"] = target_info.ssh_key or ""
        env["HOP3_SECRET_KEY"] = E2E_TEST_SECRET_KEY

        # Always add -y flag to skip confirmations in E2E tests
        cmd_args = ["hop3", *args, "-y"]

        result = subprocess.run(
            cmd_args,
            env=env,
            cwd=hermetic_cli_cwd(),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )

        return CommandResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            duration=time.time() - start_time,
        )

    # Pressure-gated disk reclaim (see ensure_disk_headroom).
    _DISK_MIN_FREE_PCT = 15
    _DISK_HARD_FLOOR_PCT = 5
    _DISK_CACHE_CEILING = "10GB"

    def ensure_disk_headroom(
        self,
        min_free_pct: int | None = None,
        hard_floor_pct: int | None = None,
        cache_ceiling: str | None = None,
    ) -> None:
        """Reclaim disk on the target when free space runs low.

        Pressure-gated, two-tier and cache-preserving:

        * **Gentle** (free < ``min_free_pct``): drop the genuinely-ephemeral
          artifacts — stopped containers, *unused per-app images*
          (``hop3/<app>:latest`` are uniquely tagged so ``image prune -f``
          misses them, yet they are never reused), dangling images — and cap
          the build cache at ``cache_ceiling``. Base images + warm cache stay,
          so repeat runs are fast and network-cheap.
        * **Escalation** (still < ``hard_floor_pct``): sacrifice the warm cache
          too — all unused images (incl. base) and the whole build cache.
          Losing cache beats failing the run.
        * **Fail** (still < ``hard_floor_pct``): raise ``TargetOutOfDiskError``
          so the caller reports one clear message instead of cascading
          misleading per-app errors (the disk is then full of non-docker data
          or simply too small).

        Best-effort otherwise (a missing ``docker``/``df`` is ignored).
        """
        min_free_pct = min_free_pct or self._DISK_MIN_FREE_PCT
        hard_floor_pct = hard_floor_pct or self._DISK_HARD_FLOOR_PCT
        cache_ceiling = cache_ceiling or self._DISK_CACHE_CEILING

        free = self._free_disk_pct()
        if free is None or free >= min_free_pct:
            return

        print(f"[disk] {free}% free on target — reclaiming ephemeral artifacts")
        self._reclaim_disk((
            "docker container prune -f",  # stopped containers (frees their images)
            # Unused per-app images: tagged, never reused; in-use ones are skipped.
            (
                "docker images 'hop3/*' --format '{{.Repository}}:{{.Tag}}'"
                " | sort -u | xargs -r docker rmi"
            ),
            "docker image prune -f",  # dangling images
            f"docker builder prune -f --keep-storage={cache_ceiling}",  # cap cache
        ))

        after = self._free_disk_pct()
        if after is not None and after < hard_floor_pct:
            print(f"[disk] still {after}% free — escalating (dropping base + cache)")
            self._reclaim_disk((
                "docker image prune -af",  # all unused images, incl. base
                "docker builder prune -af",  # all build cache
            ))
            after = self._free_disk_pct()

        if after is not None and after < hard_floor_pct:
            msg = (
                f"Target out of disk: {after}% free after full reclaim "
                f"(floor {hard_floor_pct}%). The disk is consumed by non-docker "
                "data (app dirs / nix store) or is simply too small."
            )
            raise TargetOutOfDiskError(msg)
        if after is not None:
            print(f"[disk] reclaimed to {after}% free")

    def _reclaim_disk(self, commands: tuple[str, ...]) -> None:
        """Run each reclaim command best-effort (a missing docker is fine)."""
        for cmd in commands:
            with contextlib.suppress(Exception):
                self.exec_run(f"{cmd} 2>/dev/null || true")

    def _free_disk_pct(self) -> int | None:
        """Percent free on the apps filesystem, or None if it can't be read."""
        try:
            code, out, _ = self.exec_run("df -P /home/hop3 2>/dev/null | tail -1")
        except Exception:
            return None
        if code != 0 or not out.strip():
            return None
        parts = out.split()
        if len(parts) < 5:
            return None
        try:
            used_pct = int(parts[4].rstrip("%"))
        except ValueError:
            return None
        return 100 - used_pct

    def deploy_app(
        self,
        app_path: Path,
        app_name: str,
        env_vars: dict[str, str] | None = None,
        timeout: int = 300,
    ) -> DeployResult:
        """Deploy an application to the target.

        This is a high-level method that creates a tarball and deploys via hop3.

        Args:
            app_path: Path to the application directory
            app_name: Name for the deployed app
            env_vars: Environment variables to set
            timeout: Deployment timeout in seconds

        Returns:
            DeployResult with deployment status
        """
        start_time = time.time()
        tarball_path: Path | None = None

        try:
            # Create tarball
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
                tarball_path = Path(f.name)

            with tarfile.open(tarball_path, "w:gz") as tar:
                tar.add(app_path, arcname=".")

            # Set environment variables if provided
            if env_vars:
                # TODO: Implement env var upload via hop3 CLI
                pass

            # Deploy via hop3 CLI
            # Read tarball and pipe to hop3 deploy
            result = self.run_command("deploy", "--app", app_name, timeout=timeout)

            duration = time.time() - start_time

            if not result.success:
                return DeployResult(
                    success=False,
                    app_name=app_name,
                    logs=result.stdout + result.stderr,
                    duration=duration,
                    error=f"Deploy failed: {result.stderr}",
                )

            # Wait for app to be ready
            app_url = self.get_app_url(app_name)

            return DeployResult(
                success=True,
                app_name=app_name,
                app_url=app_url,
                logs=result.stdout,
                duration=duration,
            )

        except Exception as e:
            return DeployResult(
                success=False,
                app_name=app_name,
                duration=time.time() - start_time,
                error=str(e),
            )
        finally:
            # Cleanup tarball
            if tarball_path and tarball_path.exists():
                tarball_path.unlink()

    def destroy_app(self, app_name: str) -> None:
        """Destroy a deployed application.

        Args:
            app_name: Name of the app to destroy

        Raises:
            DeploymentError: If destruction fails.
        """
        result = self.run_command("destroy", "--app", app_name)
        if not result.success:
            msg = f"Failed to destroy app '{app_name}': {result.stderr}"
            raise DeploymentError(msg)

    def get_app_url(self, app_name: str) -> str:
        """Get the URL for an application.

        Args:
            app_name: Name of the application

        Returns:
            URL to access the application
        """
        # Default: use http_base from target info
        return f"{self.info.http_base}/{app_name}"

    def http_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: int = 30,
    ) -> HttpResponse:
        """Make an HTTP request to the target.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            headers: Optional headers
            body: Optional request body
            timeout: Request timeout in seconds

        Returns:
            HttpResponse with status, body, and headers
        """
        start_time = time.time()

        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                content=body,
                timeout=timeout,
                follow_redirects=True,
            )

            return HttpResponse(
                status=response.status_code,
                body=response.text,
                headers=dict(response.headers),
                duration=time.time() - start_time,
            )
        except httpx.TimeoutException:
            return HttpResponse(
                status=0,
                body="",
                headers={"error": "timeout"},
                duration=time.time() - start_time,
            )
        except Exception as e:
            return HttpResponse(
                status=0,
                body="",
                headers={"error": str(e)},
                duration=time.time() - start_time,
            )

    def wait_for_app(
        self,
        app_name: str,
        timeout: int = 60,
        poll_interval: int = 2,
    ) -> bool:
        """Wait for an application to be running.

        Args:
            app_name: Name of the application
            timeout: Maximum wait time in seconds
            poll_interval: Time between status checks

        Returns:
            True if app is running, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            result = self.run_command("app", "status", "--app", app_name)
            if result.success and "RUNNING" in result.stdout.upper():
                return True
            time.sleep(poll_interval)

        return False

    def __enter__(self) -> Self:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()
