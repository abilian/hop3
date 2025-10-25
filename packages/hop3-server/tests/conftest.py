# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Root conftest for hop3-server tests - provides deployment target fixtures."""

from __future__ import annotations

import pytest
from hop3_testing.apps import AppSourceCatalog
from hop3_testing.targets import DeploymentTarget, DockerTarget, RemoteTarget


# 1. Add command-line options to pytest
def pytest_addoption(parser):
    """Adds custom command-line options for test configuration."""
    # Options for the 'remote' target
    parser.addoption(
        "--host", action="store", help="Remote target hostname (for --target=remote)"
    )
    parser.addoption(
        "--ssh-key", action="store", help="Path to SSH key for remote target"
    )
    # Options for the 'docker' target
    parser.addoption(
        "--keep-target",
        action="store_true",
        default=False,
        help="Keep Docker target running after tests",
    )
    parser.addoption(
        "--force-rebuild",
        action="store_true",
        default=False,
        help="Force rebuild of Docker image without cache",
    )
    parser.addoption(
        "--use-cache",
        action="store_true",
        default=False,
        help="Use existing Docker image if available, skip build",
    )


# 2. Create a session-scoped fixture for the deployment target
@pytest.fixture(scope="session")
def deployment_target(request):
    """
    Manages the lifecycle of the deployment target for the entire test session.
    Starts the target before tests run and stops it after they complete.
    """
    keep_target = request.config.getoption("--keep-target")
    host = request.config.getoption("--host")

    target: DeploymentTarget

    if host:
        remote_config = {
            "host": host,
            "ssh_key": request.config.getoption("--ssh-key"),
        }
        target_name = "remote"
        target = RemoteTarget(remote_config)
    else:
        docker_config = {
            "rebuild": not request.config.getoption("--use-cache"),
            "force_rebuild": request.config.getoption("--force-rebuild"),
            "use_cache": request.config.getoption("--use-cache"),
        }
        target_name = "docker"
        target = DockerTarget(docker_config)

    try:
        print(f"Starting deployment target '{target_name}' for test session...")
        target.start()
        yield target
    finally:
        if not keep_target:
            print(f"Stopping deployment target '{target_name}'...")
            target.stop()
        else:
            print(f"Keeping deployment target '{target_name}' running as requested.")


# 3. Create a fixture for the test app catalog
@pytest.fixture(scope="session")
def app_catalog():
    """Provides a TestAppCatalog instance for accessing test applications."""
    return AppSourceCatalog()
