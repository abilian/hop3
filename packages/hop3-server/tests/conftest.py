# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Root conftest for hop3-server tests - provides deployment target fixtures."""

from __future__ import annotations

import json

import pytest
from filelock import FileLock
from hop3_testing.catalog import TestCatalog
from hop3_testing.targets import (
    DeploymentConfig,
    DeploymentTarget,
    DockerConfig,
    DockerTarget,
    RemoteConfig,
    RemoteTarget,
)
from hop3_testing.targets.helpers import find_project_root

from hop3.orm import reset_session_factory_cache

from .di_fixtures import di_container  # noqa: F401


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
        help="Force rebuild of Docker image without layer cache",
    )


# 2. Create a session-scoped fixture for the deployment target
@pytest.fixture(scope="session")
def deployment_target(request, tmp_path_factory):
    """
    Manages the lifecycle of the deployment target for the entire test session.
    Starts the target before tests run and stops it after they complete.

    Supports pytest-xdist parallel execution by sharing a single container
    across all workers using a lock file.
    """
    keep_target = request.config.getoption("--keep-target")
    host = request.config.getoption("--host")

    # Check if running under pytest-xdist
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    is_xdist = worker_id != "master"

    target: DeploymentTarget

    if host:
        remote_config = RemoteConfig(
            host=host,
            ssh_key=request.config.getoption("--ssh-key"),
        )
        target_name = "remote"
        target = RemoteTarget(remote_config)
        # Remote targets don't need special xdist handling
        try:
            print(f"Starting deployment target '{target_name}' for test session...")
            target.start()
            yield target
        finally:
            if not keep_target:
                print(f"Stopping deployment target '{target_name}'...")
                target.stop()
            else:
                print(
                    f"Keeping deployment target '{target_name}' running as requested."
                )
        return

    # Docker target with xdist support
    # Deploy Hop3 from local code to the container
    docker_config = DockerConfig(
        container_name="hop3-server-test",
    )
    # Deploy Hop3 from local source code
    deployment_config = DeploymentConfig(
        source="local",
        clean=False,
        verbose=False,
    )

    if is_xdist:
        # Running under pytest-xdist - share container across workers
        root_tmp = tmp_path_factory.getbasetemp().parent
        lock_file = root_tmp / "deployment_target.lock"
        info_file = root_tmp / "deployment_target.json"

        # Use filelock for coordination (built into pytest-xdist)
        with FileLock(str(lock_file)):
            if info_file.exists():
                # Another worker already started the container - reuse it
                info_data = json.loads(info_file.read_text())
                print(f"Worker {worker_id}: Reusing shared deployment target...")
                reuse_config = DockerConfig(
                    container_name=info_data.get("container_name", "hop3-server-test"),
                    reuse_container=True,
                )
                target = DockerTarget(reuse_config)
                target.start()
                yield target
                # Don't stop - let the master worker handle cleanup
                return
            else:
                # First worker - start the container and share info
                print(f"Worker {worker_id}: Starting shared deployment target...")
                target = DockerTarget(docker_config, deployment=deployment_config)
                target.start()
                # Save connection info for other workers
                info_data = {
                    "container_name": docker_config.container_name,
                    "ssh_port": target._info.ssh_port,
                    "http_base": target._info.http_base,
                    "api_url": target._info.api_url,
                    "ssh_key": target._info.ssh_key,
                }
                info_file.write_text(json.dumps(info_data))
                yield target
                # Only first worker cleans up
                if not keep_target:
                    print(f"Worker {worker_id}: Stopping shared deployment target...")
                    target.stop()
                return

    # Not running under xdist - normal single-process behavior
    target_name = "docker"
    target = DockerTarget(docker_config, deployment=deployment_config)

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


# 3. Create a fixture for the test catalog
@pytest.fixture(scope="session")
def test_catalog():
    """Provides a TestCatalog instance for accessing test definitions."""
    try:
        root = find_project_root()
    except RuntimeError:
        root = None
    catalog = TestCatalog(root)
    catalog.scan()
    return catalog


# 4. Reset session factory cache before each test to ensure test isolation
@pytest.fixture(autouse=True)
def reset_session_factory():
    """Reset session factory cache before each test to prevent database state pollution.

    This ensures that each test gets a fresh database connection and prevents
    tests from accidentally sharing database state through the session factory cache.
    """
    reset_session_factory_cache()
    yield
    reset_session_factory_cache()
