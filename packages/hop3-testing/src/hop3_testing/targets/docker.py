# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Docker-based deployment target."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import docker
from docker.errors import BuildError, ImageNotFound

from .base import DeploymentTarget, TargetInfo

if TYPE_CHECKING:
    from collections.abc import Iterator


class DockerTarget(DeploymentTarget):
    """Docker container-based deployment target.

    This target creates a Docker container running Hop3 server for testing.
    It uses the same Docker image as the E2E tests.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize Docker target.

        Args:
            config: Configuration dictionary with optional keys:
                - image_tag: Docker image tag (default: "hop3-e2e:test")
                - dockerfile: Path to Dockerfile (default: auto-detect)
                - force_rebuild: Disable Docker layer cache for full rebuild (default: False)
                - container_name: Name for the container (default: auto-generated)
                - ports: Custom port mappings (default: auto-assign)
        """
        super().__init__(config)
        self.client = docker.from_env()
        self.container = None
        self.ssh_key_path: Path | None = None

        # Configuration
        self.image_tag = (
            config.get("image_tag", "hop3-e2e:test") if config else "hop3-e2e:test"
        )
        self.container_name = config.get("container_name") if config else None
        self.force_rebuild = config.get("force_rebuild", False) if config else False

    def _build_image(self, *, force: bool = False) -> None:
        """Build the Docker image.

        Args:
            force: Force rebuild without using Docker layer cache (nocache=True)
        """
        # Check if image exists
        image_exists = False
        try:
            self.client.images.get(self.image_tag)
            image_exists = True
        except ImageNotFound:
            pass

        # Always build (with Docker layer caching unless force=True)
        print(f"Building Docker image: {self.image_tag}")
        if force:
            print("(Force rebuild - ignoring Docker layer cache)")
        elif image_exists:
            print("(Docker will use cached layers where possible)")
        else:
            print("(First build - this may take 5-10 minutes...)")

        # Find project root (up from packages/hop3-testing)
        # Path: .../hop3/packages/hop3-testing/src/hop3_testing/targets/docker.py
        current_file = Path(__file__)
        # Go up: targets/ -> hop3_testing/ -> src/ -> hop3-testing/ -> packages/ -> hop3/
        project_root = current_file.parent.parent.parent.parent.parent.parent
        dockerfile_path = (
            project_root / "packages/hop3-server/tests/d_e2e/docker/Dockerfile"
        )

        if not dockerfile_path.exists():
            msg = f"Dockerfile not found at {dockerfile_path}"
            raise FileNotFoundError(msg)

        # Build hop3-server distribution first
        print("Building hop3-server distribution...")
        subprocess.run(
            ["uv", "build", "packages/hop3-server"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        # Build Docker image with layer caching
        try:
            _image, logs = self.client.images.build(
                path=str(project_root),
                dockerfile=str(dockerfile_path),
                tag=self.image_tag,
                rm=True,  # Remove intermediate containers
                forcerm=True,  # Always remove intermediate containers
                nocache=force,  # Only disable cache when force=True
            )

            # Print build logs
            for log in logs:
                if "stream" in log:
                    print(log["stream"].strip())

            print(f"Successfully built image: {self.image_tag}")

        except BuildError as e:
            print(f"Build failed: {e}")
            for log in e.build_log:
                if "stream" in log:
                    print(log["stream"].strip())
            msg = f"Failed to build Docker image: {e}"
            raise RuntimeError(msg) from e

    def start(self) -> TargetInfo:
        """Start the Docker container.

        Returns:
            TargetInfo with connection details
        """
        # Always build image (Docker layer caching makes this fast if nothing changed)
        self._build_image(force=self.force_rebuild)

        print("\n" + "=" * 60)
        print("Starting Hop3 Docker container...")
        print("=" * 60)

        # Start container
        self.container = self.client.containers.run(
            self.image_tag,
            name=self.container_name,
            detach=True,
            ports={
                "22/tcp": None,  # SSH - random port
                "80/tcp": None,  # HTTP - random port
                "8000/tcp": None,  # Hop3 server - random port
            },
            remove=False,  # Don't auto-remove to allow inspection
        )

        # Wait for services to initialize
        print("Waiting for services to initialize...")
        time.sleep(5)

        # Check if container is still running
        self.container.reload()
        if self.container.status != "running":
            print(f"\n❌ Container exited with status: {self.container.status}")
            print("Container logs:")
            print(self.container.logs().decode())
            msg = f"Container failed to start (status: {self.container.status})"
            raise RuntimeError(msg)

        # Wait for hop3-server to be ready
        if not self._wait_for_ready():
            self._dump_logs()
            msg = "hop3-server failed to start"
            raise RuntimeError(msg)

        # Get connection info
        self._info = self._get_connection_info()

        print("\nContainer ready:")
        print(
            f"  SSH: ssh -i {self._info.ssh_key} -p {self._info.ssh_port} hop3@localhost"
        )
        print(f"  HTTP: {self._info.http_base}")
        print(f"  API: {self._info.api_url}")
        print("=" * 60 + "\n")

        return self._info

    def _wait_for_ready(self, max_wait: int = 60) -> bool:
        """Wait for hop3-server to be ready.

        Args:
            max_wait: Maximum time to wait in seconds

        Returns:
            True if server is ready, False otherwise
        """
        print("Waiting for hop3-server to be ready...")
        start_time = time.time()

        while time.time() - start_time < max_wait:
            # Check container is still running
            self.container.reload()
            if self.container.status != "running":
                print(f"\n❌ Container exited during startup: {self.container.status}")
                return False

            # Check if hop3-server is responding
            try:
                result = self.container.exec_run(
                    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'"
                )
                # Accept 200 (OK) or 404 (no route but server responding)
                if b"200" in result.output or b"404" in result.output:
                    print("✓ hop3-server is responding")
                    return True
            except Exception as e:
                print(f"Warning: Failed to check server health: {e}")

            time.sleep(2)

        print("\n⚠ hop3-server did not start in time")
        return False

    def _dump_logs(self) -> None:
        """Dump container logs for debugging."""
        print("\nSupervisor stdout logs:")
        try:
            result = self.container.exec_run("cat /var/log/supervisor/hop3-server.log")
            print(result.output.decode())
        except Exception as e:
            print(f"Could not get hop3-server stdout logs: {e}")

        print("\nSupervisor stderr logs:")
        try:
            result = self.container.exec_run(
                "cat /var/log/supervisor/hop3-server_err.log"
            )
            print(result.output.decode())
        except Exception as e:
            print(f"Could not get hop3-server stderr logs: {e}")

        print("\nContainer logs:")
        print(self.container.logs().decode())

    def _get_connection_info(self) -> TargetInfo:
        """Get connection information for the container.

        Returns:
            TargetInfo with connection details
        """
        # Get port mappings
        self.container.reload()
        ports = self.container.attrs["NetworkSettings"]["Ports"]

        ssh_port = int(ports["22/tcp"][0]["HostPort"])
        http_port = int(ports["80/tcp"][0]["HostPort"])
        api_port = int(ports["8000/tcp"][0]["HostPort"])

        # Get SSH key
        ssh_key_result = self.container.exec_run("cat /home/hop3/.ssh/id_rsa")
        ssh_key = ssh_key_result.output.decode()

        # Save SSH key to temp file
        self.ssh_key_path = Path("/tmp") / f"hop3-e2e-key-{self.container.short_id}"
        self.ssh_key_path.write_text(ssh_key)
        self.ssh_key_path.chmod(0o600)

        return TargetInfo(
            ssh_host="hop3@localhost",
            ssh_port=ssh_port,
            ssh_key=str(self.ssh_key_path),
            http_base=f"http://localhost:{http_port}",
            api_url=f"http://localhost:{api_port}",
            metadata={
                "container_id": self.container.id,
                "container_name": self.container.name,
            },
        )

    def _reuse_container(self, info_data: dict) -> None:
        """Reuse an existing container started by another worker.

        Args:
            info_data: Dictionary with container_id and connection info
        """
        container_id = info_data["container_id"]
        self.container = self.client.containers.get(container_id)

        # Restore SSH key
        self.ssh_key_path = Path(info_data["ssh_key"])

        # Restore target info
        self._info = TargetInfo(
            ssh_host="hop3@localhost",
            ssh_port=info_data["ssh_port"],
            ssh_key=info_data["ssh_key"],
            http_base=info_data["http_base"],
            api_url=info_data["api_url"],
            metadata={
                "container_id": container_id,
                "reused": True,
            },
        )

    def stop(self) -> None:
        """Stop and remove the container."""
        if not self.container:
            return

        print("\nStopping container...")
        try:
            self.container.reload()
            if self.container.status == "running":
                self.container.stop(timeout=10)
            self.container.remove(force=True)
        except Exception as e:
            print(f"Warning: Error stopping container: {e}")

        # Remove SSH key
        if self.ssh_key_path and self.ssh_key_path.exists():
            self.ssh_key_path.unlink()

        print("Container stopped and removed.")

    def is_ready(self) -> bool:
        """Check if the container is ready.

        Returns:
            True if container is running and hop3-server is responding
        """
        if not self.container:
            return False

        try:
            self.container.reload()
            if self.container.status != "running":
                return False

            # Quick health check
            result = self.container.exec_run(
                "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'"
            )
            return b"200" in result.output or b"404" in result.output
        except Exception:
            return False

    def exec_run(self, cmd: str | list[str]) -> tuple[int, str, str]:
        """Execute a command in the container.

        Args:
            cmd: Command to execute

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        if not self.container:
            msg = "Container not started"
            raise RuntimeError(msg)

        if isinstance(cmd, list):
            cmd = " ".join(cmd)

        result = self.container.exec_run(cmd, demux=True)
        exit_code = result.exit_code
        stdout_bytes, stderr_bytes = result.output

        stdout = stdout_bytes.decode() if stdout_bytes else ""
        stderr = stderr_bytes.decode() if stderr_bytes else ""

        return exit_code, stdout, stderr

    def get_logs(self) -> Iterator[str]:
        """Get container logs.

        Yields:
            Log lines
        """
        if not self.container:
            return

        for line in self.container.logs(stream=True):
            yield line.decode()
