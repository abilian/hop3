# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pytest configuration and fixtures for Hop3 deployment testing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hop3_testing.apps import TestAppCatalog
from hop3_testing.targets import DockerTarget, RemoteTarget

if TYPE_CHECKING:
    from collections.abc import Generator

    from hop3_testing.targets.base import DeploymentTarget


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--target",
        action="store",
        default="docker",
        choices=["docker", "remote"],
        help="Deployment target type (default: docker)",
    )
    parser.addoption(
        "--target-host",
        action="store",
        help="Remote target hostname (for remote target)",
    )
    parser.addoption(
        "--target-port",
        action="store",
        type=int,
        default=22,
        help="Remote target SSH port (for remote target)",
    )
    parser.addoption(
        "--target-user",
        action="store",
        default="hop3",
        help="Remote target SSH user (for remote target)",
    )
    parser.addoption(
        "--target-ssh-key",
        action="store",
        help="Remote target SSH key path (for remote target)",
    )
    parser.addoption(
        "--apps-dir",
        action="store",
        help="Path to test apps directory (default: auto-detect)",
    )
    parser.addoption(
        "--app-category",
        action="store",
        help="Filter tests by app category",
    )
    parser.addoption(
        "--keep-container",
        action="store_true",
        default=False,
        help="Keep Docker container running after tests",
    )
    parser.addoption(
        "--use-cache",
        action="store_true",
        default=False,
        help="Use cached Docker image instead of rebuilding",
    )


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "deployment: Deployment tests requiring a Hop3 server",
    )
    config.addinivalue_line(
        "markers",
        "docker: Tests that require Docker",
    )
    config.addinivalue_line(
        "markers",
        "remote: Tests that require a remote server",
    )
    config.addinivalue_line(
        "markers",
        "slow: Slow-running tests",
    )


@pytest.fixture(scope="session")
def target_config(request) -> dict:
    """Get target configuration from pytest options or environment.

    Returns:
        Configuration dictionary for the target
    """
    target_type = request.config.getoption("--target")

    if target_type == "remote":
        # Get config from command line or environment
        host = request.config.getoption("--target-host") or os.getenv("HOP3_TEST_HOST")
        if not host:
            pytest.skip("Remote target requires --target-host or HOP3_TEST_HOST")

        port = request.config.getoption("--target-port") or int(
            os.getenv("HOP3_TEST_PORT", "22")
        )
        user = request.config.getoption("--target-user") or os.getenv(
            "HOP3_TEST_USER", "hop3"
        )
        ssh_key = request.config.getoption("--target-ssh-key") or os.getenv(
            "HOP3_TEST_SSH_KEY"
        )

        return {
            "type": "remote",
            "host": host,
            "port": port,
            "user": user,
            "ssh_key": ssh_key,
        }

    # Docker target (default)
    use_cache = request.config.getoption("--use-cache", default=False)
    return {
        "type": "docker",
        "image_tag": "hop3-e2e:test",
        "rebuild": not use_cache,  # Rebuild by default unless --use-cache
        "use_cache": use_cache,
    }


@pytest.fixture(scope="session")
def deployment_target(
    request, target_config: dict
) -> Generator[DeploymentTarget, None, None]:
    """Create and manage a deployment target for the test session.

    This fixture creates a deployment target (Docker or Remote) and manages
    its lifecycle for the entire test session.

    Yields:
        DeploymentTarget instance
    """
    target_type = target_config.get("type", "docker")

    # Create target
    if target_type == "remote":
        target = RemoteTarget(target_config)
    else:
        target = DockerTarget(target_config)

    # Start target
    target.start()

    # Wait for target to be ready
    if not target.is_ready():
        pytest.fail("Deployment target is not ready")

    yield target

    # Stop target (unless --keep-container is set for Docker)
    keep = request.config.getoption("--keep-container", default=False)
    if not (target_type == "docker" and keep):
        target.stop()


@pytest.fixture
def test_app_catalog(request) -> TestAppCatalog:
    """Get test application catalog.

    Returns:
        TestAppCatalog instance
    """
    apps_dir = request.config.getoption("--apps-dir")
    if apps_dir:
        apps_dir = Path(apps_dir)

    return TestAppCatalog(apps_dir=apps_dir)


@pytest.fixture
def test_apps(request, test_app_catalog: TestAppCatalog):
    """Get filtered test applications.

    Returns:
        List of TestApp instances based on filters
    """
    category = request.config.getoption("--app-category")

    if category:
        return list(test_app_catalog.filter(category=category))

    return list(test_app_catalog)


@pytest.fixture
def simple_apps(test_app_catalog: TestAppCatalog):
    """Get simple test applications (static and basic Python/Node.js).

    Returns:
        List of simple TestApp instances
    """
    apps = []
    apps.extend(test_app_catalog.filter(category="static"))
    apps.extend(test_app_catalog.filter(category="python-simple"))
    return list(apps)
