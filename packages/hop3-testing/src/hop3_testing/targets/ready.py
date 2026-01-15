# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pre-built Docker target for app testing.

This target uses a pre-built Docker image with Hop3 already installed,
skipping the deployment step for faster app testing iteration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import docker

from hop3_testing.diagnostics import DiagnosticCollector

from .base import DeploymentTarget, TargetInfo
from .constants import DEFAULT_READY_IMAGE, DEFAULT_READY_IMAGE_HEALTH_TIMEOUT
from .helpers import DiagnosticsHelper, HealthChecker


class ReadyTarget(DeploymentTarget):
    """Uses a pre-built Docker image for app testing.

    This target does NOT deploy Hop3 - it expects the image to already
    have Hop3 installed and ready. This is used for:
    - App testing (testing apps, not Hop3)
    - Fast iteration (skip 5+ minute installation)
    - CI pipelines (use cached image)

    Args:
        config: Configuration dictionary with optional keys:
            - image: Docker image to use (default: "hop3-ready:latest")
            - container_name: Override container name
            - verbose: Verbose output (default: False)
            - log_dir: Directory for diagnostic logs
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.config = config or {}

        # Setup diagnostics with file logging
        log_dir = self.config.get("log_dir")
        self.diagnostics = DiagnosticCollector(
            verbose=self.config.get("verbose", False),
            log_dir=Path(log_dir) if log_dir else None,
        )

        # Compose helpers
        self._diagnostics_helper = DiagnosticsHelper(self.diagnostics)
        self._health_checker = HealthChecker(
            self.diagnostics,
            timeout=DEFAULT_READY_IMAGE_HEALTH_TIMEOUT,
        )

        self.image = self.config.get("image", DEFAULT_READY_IMAGE)
        self.container_name = self.config.get("container_name", "hop3-app-test")

        self._container = None
        self._started = False

    def start(self) -> TargetInfo:
        """Start the pre-built container.

        Returns:
            TargetInfo with connection details
        """
        # Initialize diagnostic context
        self.diagnostics.set_context(
            test_name=f"apps-{self.container_name}",
            config="ready",
        )
        self.diagnostics.set_phase("setup")

        print("\n" + "=" * 70)
        print(f"Starting pre-built container: {self.image}")
        print("(No deployment - image should have Hop3 pre-installed)")
        print("=" * 70)

        try:
            client = docker.from_env()

            # Check if image exists
            try:
                client.images.get(self.image)
                self.diagnostics.add_success(
                    layer="docker",
                    operation="check_image",
                    message=f"Image {self.image} found",
                )
            except docker.errors.ImageNotFound:
                self.diagnostics.add_failure(
                    layer="docker",
                    operation="check_image",
                    message=f"Image {self.image} not found",
                    details={
                        "hint": "Build with: hop3-test-new build-ready-image",
                    },
                )
                msg = f"Image {self.image} not found. Build it with: hop3-test-new build-ready-image"
                raise RuntimeError(msg) from None

            # Remove any existing container with the same name
            try:
                existing = client.containers.get(self.container_name)
                print(f"Removing existing container: {self.container_name}")
                existing.remove(force=True)
            except docker.errors.NotFound:
                pass  # No existing container, good

            # Start container
            self._container = client.containers.run(
                self.image,
                name=self.container_name,
                detach=True,
                ports={
                    "22/tcp": None,
                    "80/tcp": None,
                    "8000/tcp": None,
                },
                remove=False,
            )

            self.diagnostics.add_success(
                layer="docker",
                operation="start_container",
                message=f"Container {self.container_name} started",
            )

            # Wait for server to be ready
            self.diagnostics.set_phase("health_check")
            if not self._health_checker.wait_for_container(self._container):
                self.diagnostics.add_failure(
                    layer="server",
                    operation="health_check",
                    message="Server did not become ready",
                )
                self._diagnostics_helper.save_on_error()
                msg = "Server did not become ready"
                raise RuntimeError(msg)

            self._info = self._build_target_info()
            self._started = True

            print("\nTarget ready:")
            print(f"  HTTP: {self._info.http_base}")
            print("=" * 70 + "\n")

            return self._info

        except Exception as e:
            self.diagnostics.add_failure(
                layer="testing",
                operation="start",
                message=f"Start failed: {e}",
            )
            self._diagnostics_helper.save_on_error()
            raise

    def _build_target_info(self) -> TargetInfo:
        """Build TargetInfo from container."""
        self._container.reload()
        ports = self._container.attrs["NetworkSettings"]["Ports"]

        ssh_port = int(ports["22/tcp"][0]["HostPort"])
        http_port = int(ports["80/tcp"][0]["HostPort"])
        api_port = int(ports["8000/tcp"][0]["HostPort"])

        # Extract SSH key
        ssh_key_path = self._extract_ssh_key()

        return TargetInfo(
            ssh_host="hop3@localhost",
            ssh_port=ssh_port,
            ssh_key=str(ssh_key_path) if ssh_key_path else None,
            http_base=f"http://localhost:{http_port}",
            api_url=f"http://localhost:{api_port}",
            metadata={
                "container_id": self._container.id,
                "container_name": self._container.name,
            },
        )

    def _extract_ssh_key(self) -> Path | None:
        """Extract SSH key from container."""
        try:
            result = self._container.exec_run("cat /home/hop3/.ssh/id_rsa")
            if result.exit_code == 0:
                key_path = Path("/tmp") / f"hop3-ready-key-{self._container.short_id}"
                key_path.write_text(result.output.decode())
                key_path.chmod(0o600)
                return key_path
        except Exception:
            pass
        return None

    def stop(self) -> None:
        """Stop and remove the container."""
        if not self._container:
            return

        self.diagnostics.set_phase("cleanup")
        print("\nStopping container...")
        try:
            self._container.reload()
            if self._container.status == "running":
                self._container.stop(timeout=10)
            self._container.remove(force=True)
            self.diagnostics.add_success(
                layer="docker",
                operation="teardown",
                message="Container stopped and removed",
            )
        except Exception as e:
            self.diagnostics.add_failure(
                layer="docker",
                operation="teardown",
                message=f"Error stopping container: {e}",
            )
            print(f"Warning: Error stopping container: {e}")

        self._started = False
        print("Container stopped.")

    def save_diagnostics(self, generate_html: bool = False) -> Path:
        """Save all diagnostic information to files."""
        return self._diagnostics_helper.save(generate_html)

    def is_ready(self) -> bool:
        """Check if the container is ready."""
        if not self._container:
            return False
        return self._health_checker.is_container_ready(self._container)

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Execute a command in the container."""
        if not self._container:
            msg = "Container not started"
            raise RuntimeError(msg)

        if isinstance(cmd, list):
            cmd = " ".join(cmd)

        result = self._container.exec_run(cmd, demux=True)
        stdout = result.output[0].decode() if result.output[0] else ""
        stderr = result.output[1].decode() if result.output[1] else ""

        return result.exit_code, stdout, stderr
