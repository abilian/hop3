# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""E2E test fixtures for installer testing.

These fixtures provide Docker container management for testing the
hop3-installer scripts in isolation.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

# Container configuration
CONTAINER_NAME = "hop3-installer-test"
BASE_IMAGE = "ubuntu:24.04"


def docker_exec(
    container: str,
    cmd: str,
    *,
    check: bool = True,
    user: str | None = None,
) -> subprocess.CompletedProcess:
    """Execute command in Docker container.

    Args:
        container: Container name or ID
        cmd: Command to execute
        check: Whether to raise on non-zero exit
        user: User to run command as (default: root)

    Returns:
        CompletedProcess with stdout/stderr captured
    """
    docker_cmd = ["docker", "exec"]
    if user:
        docker_cmd.extend(["-u", user])
    docker_cmd.extend([container, "bash", "-c", cmd])

    return subprocess.run(
        docker_cmd,
        capture_output=True,
        text=True,
        check=check,
    )


def docker_copy(container: str, src: Path, dest: str) -> None:
    """Copy file to Docker container.

    Args:
        container: Container name or ID
        src: Local source path
        dest: Remote destination path
    """
    subprocess.run(
        ["docker", "cp", str(src), f"{container}:{dest}"],
        check=True,
    )


def docker_copy_dir(container: str, src: Path, dest: str) -> None:
    """Copy directory to Docker container.

    Args:
        container: Container name or ID
        src: Local source directory
        dest: Remote destination path
    """
    subprocess.run(
        ["docker", "cp", str(src), f"{container}:{dest}"],
        check=True,
    )
    # Fix permissions so all users can read
    docker_exec(container, f"chmod -R a+rX {dest}", check=False)


@pytest.fixture(scope="module")
def docker_container() -> Generator[str, None, None]:
    """Create and manage a Docker container for testing.

    This fixture:
    1. Removes any existing test container
    2. Starts a fresh Ubuntu container
    3. Installs Python and prerequisites
    4. Yields the container name
    5. Cleans up after tests complete

    Yields:
        Container name for use in tests
    """
    # Check Docker is available
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Docker not available")

    # Remove any existing container
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
        check=False,
    )

    # Start fresh container
    # Note: We use sleep infinity instead of systemd for simplicity
    # Service validation tests will be skipped without systemd
    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            BASE_IMAGE,
            "sleep",
            "infinity",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to start container: {result.stderr}")

    # Wait for container to be ready
    time.sleep(1)

    # Install prerequisites
    docker_exec(
        CONTAINER_NAME,
        "apt-get update -qq && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
        "python3 python3-venv python3-pip git curl sudo ca-certificates",
    )

    yield CONTAINER_NAME

    # Cleanup
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
        check=False,
    )


@pytest.fixture(scope="module")
def bundled_installers(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Generate bundled installer scripts.

    This fixture generates the single-file installer scripts using the bundler.

    Returns:
        Dict with 'cli' and 'server' keys pointing to installer paths
    """
    from hop3_installer.bundler import bundle_installer

    out_dir = tmp_path_factory.mktemp("installers")

    # Generate CLI installer
    cli_content = bundle_installer("cli")
    cli_path = out_dir / "install-cli.py"
    cli_path.write_text(cli_content)
    cli_path.chmod(0o755)

    # Generate server installer
    server_content = bundle_installer("server")
    server_path = out_dir / "install-server.py"
    server_path.write_text(server_content)
    server_path.chmod(0o755)

    return {"cli": cli_path, "server": server_path}


@pytest.fixture(scope="module")
def hop3_packages_dir() -> Path:
    """Get the path to the hop3 packages directory.

    Returns:
        Path to packages/ directory in the repository
    """
    # Navigate from this file to the packages directory
    # tests/c_e2e/conftest.py -> packages/hop3-installer/tests/c_e2e/conftest.py
    this_file = Path(__file__)
    packages_dir = this_file.parent.parent.parent.parent.parent / "packages"

    if not packages_dir.exists():
        pytest.fail(f"Packages directory not found: {packages_dir}")

    return packages_dir
