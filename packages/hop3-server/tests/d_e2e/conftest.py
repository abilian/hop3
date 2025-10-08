# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pytest configuration for Docker-based E2E tests."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import docker
import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


def pytest_configure(config):
    """Add custom markers."""
    config.addinivalue_line(
        "markers",
        "e2e: Full end-to-end tests requiring Docker containers",
    )


@pytest.fixture(scope="session")
def docker_client() -> Generator[docker.DockerClient, None, None]:
    """Provide Docker client for tests."""
    try:
        client = docker.from_env()
        # Test Docker connectivity
        client.ping()
        yield client
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")
    finally:
        if "client" in locals():
            client.close()


@pytest.fixture(scope="session")
def hop3_image(docker_client: docker.DockerClient) -> str:
    """Build hop3 E2E test image if not already built."""
    image_tag = "hop3-e2e:test"

    # Check if image already exists
    try:
        docker_client.images.get(image_tag)
        print(f"Using existing Docker image: {image_tag}")
        return image_tag
    except docker.errors.ImageNotFound:
        pass

    # Build the image
    print(f"Building Docker image: {image_tag}")
    print("This may take 5-10 minutes on first run...")

    project_root = Path(__file__).parent.parent.parent.parent.parent
    # Use simple Dockerfile that works on macOS (no systemd)
    dockerfile_path = Path(__file__).parent / "docker" / "Dockerfile.simple"

    # Build hop3 distribution first
    print("Building hop3-server distribution...")
    subprocess.run(
        ["uv", "build", "packages/hop3-server"],
        cwd=project_root,
        check=True,
    )

    # Build Docker image
    try:
        _image, logs = docker_client.images.build(
            path=str(project_root),
            dockerfile=str(dockerfile_path),
            tag=image_tag,
            rm=True,  # Remove intermediate containers
            forcerm=True,  # Always remove intermediate containers
        )

        # Print build logs
        for log in logs:
            if "stream" in log:
                print(log["stream"].strip())

        print(f"Successfully built image: {image_tag}")
        return image_tag

    except docker.errors.BuildError as e:
        print(f"Build failed: {e}")
        for log in e.build_log:
            if "stream" in log:
                print(log["stream"].strip())
        pytest.fail(f"Failed to build Docker image: {e}")


@pytest.fixture(scope="class")
def hop3_container(
    docker_client: docker.DockerClient, hop3_image: str
) -> Generator[dict[str, Any], None, None]:
    """Start a hop3 container for E2E tests.

    Scope: class - new container for each test class.
    """
    print("\n" + "=" * 60)
    print("Starting hop3 E2E test container...")
    print("=" * 60)

    # Start container (using supervisor, not systemd)
    container = docker_client.containers.run(
        hop3_image,
        detach=True,
        ports={
            "22/tcp": None,  # SSH - random port
            "80/tcp": None,  # HTTP - random port
            "8000/tcp": None,  # Hop3 server - random port
        },
    )

    try:
        # Wait for services to initialize
        print("Waiting for services to initialize...")
        time.sleep(5)

        # Check if container is still running
        container.reload()
        if container.status != "running":
            print(f"\n❌ Container exited with status: {container.status}")
            print("Container logs:")
            print(container.logs().decode())
            pytest.fail(f"Container failed to start (status: {container.status})")

        # Wait for hop3-server to be ready
        print("Waiting for hop3-server to be ready...")
        max_wait = 60
        start_time = time.time()

        while time.time() - start_time < max_wait:
            # Check container is still running
            container.reload()
            if container.status != "running":
                print(f"\n❌ Container exited during startup: {container.status}")
                print("Container logs:")
                print(container.logs().decode())
                pytest.fail(
                    f"Container stopped unexpectedly (status: {container.status})"
                )

            # Check if hop3-server is responding (check root endpoint)
            try:
                result = container.exec_run(
                    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || echo '000'"
                )
                # Accept 200 (OK) or 404 (no route but server responding)
                if b"200" in result.output or b"404" in result.output:
                    print("✓ hop3-server is responding")
                    break
            except Exception as e:
                print(f"Warning: Failed to check server health: {e}")

            time.sleep(2)
        else:
            # Timeout - dump logs for debugging
            print("\n⚠ hop3-server did not start in time")
            print("\nSupervisor stdout logs:")
            try:
                result = container.exec_run("cat /var/log/supervisor/hop3-server.log")
                print(result.output.decode())
            except Exception as e:
                print(f"Could not get hop3-server stdout logs: {e}")

            print("\nSupervisor stderr logs:")
            try:
                result = container.exec_run(
                    "cat /var/log/supervisor/hop3-server_err.log"
                )
                print(result.output.decode())
            except Exception as e:
                print(f"Could not get hop3-server stderr logs: {e}")

            print("\nContainer logs:")
            print(container.logs().decode())
            pytest.fail("hop3-server failed to start")

        # Get container info
        container.reload()
        ports = container.attrs["NetworkSettings"]["Ports"]

        # Extract host ports
        ssh_port = ports["22/tcp"][0]["HostPort"]
        http_port = ports["80/tcp"][0]["HostPort"]
        api_port = ports["8000/tcp"][0]["HostPort"]

        # Get SSH key for passwordless access
        ssh_key_result = container.exec_run("cat /home/hop3/.ssh/id_rsa")
        ssh_key = ssh_key_result.output.decode()

        # Save SSH key to temp file
        ssh_key_path = Path("/tmp") / f"hop3-e2e-key-{container.short_id}"
        ssh_key_path.write_text(ssh_key)
        ssh_key_path.chmod(0o600)

        container_info = {
            "container": container,
            "ssh_host": "hop3@localhost",
            "ssh_port": int(ssh_port),
            "ssh_key": str(ssh_key_path),
            "http_base": f"http://localhost:{http_port}",
            "api_url": f"http://localhost:{api_port}",
        }

        print("\nContainer ready:")
        print(f"  SSH: ssh -i {ssh_key_path} -p {ssh_port} hop3@localhost")
        print(f"  HTTP: {container_info['http_base']}")
        print(f"  API: {container_info['api_url']}")
        print("=" * 60 + "\n")

        yield container_info

    finally:
        # Cleanup
        print("\nStopping container...")
        try:
            container.reload()
            if container.status == "running":
                container.stop(timeout=10)
            container.remove(force=True)
        except Exception as e:
            print(f"Warning: Error stopping container: {e}")

        # Remove SSH key
        if "ssh_key_path" in locals() and ssh_key_path.exists():
            ssh_key_path.unlink()

        print("Container stopped and removed.")


@pytest.fixture
def test_app_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test applications."""
    app_dir = tmp_path / "test-app"
    app_dir.mkdir()
    return app_dir


def run_hop3_command(
    container_info: dict[str, Any], *args: str
) -> subprocess.CompletedProcess:
    """Run a hop3 CLI command against the container.

    Args:
        container_info: Container information dict from hop3_container fixture
        *args: Arguments to pass to hop3 command

    Returns:
        CompletedProcess with stdout, stderr, and returncode
    """
    ssh_key = container_info["ssh_key"]
    ssh_port = container_info["ssh_port"]

    # Set environment for hop3 CLI
    env = os.environ.copy()
    env["HOP3_API_URL"] = f"ssh://hop3@localhost:{ssh_port}"
    env["HOP3_SSH_KEY"] = ssh_key
    # Use the same secret key configured in the container
    env["HOP3_SECRET_KEY"] = "e2e-test-secret-key-do-not-use-in-production"

    cmd = ["hop3", *args]

    result = subprocess.run(
        cmd,
        check=False, env=env,
        capture_output=True,
        text=True,
    )

    return result


@pytest.fixture
def hop3_command(hop3_container: dict[str, Any]):
    """Provide a helper to run hop3 commands."""

    def _run(*args: str) -> subprocess.CompletedProcess:
        return run_hop3_command(hop3_container, *args)

    return _run
