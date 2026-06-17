# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Pytest fixtures for E2E installer tests.

Provides multi-backend support for testing installers on:
- Docker containers (default)
- SSH hosts (when HOP3_TEST_HOST is set or --ssh-host is provided)
- Vagrant VMs (when --vagrant is used)

CLI options:
    --docker        Enable Docker backend
    --ssh           Enable SSH backend (requires HOP3_TEST_HOST or --ssh-host)
    --ssh-host HOST Specify SSH host (implies --ssh)
    --vagrant       Enable Vagrant backend

If no backend options are specified, defaults to Docker + SSH (if configured).
If any backend option is specified, only those backends are enabled.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from .utils import bundle_installers, get_backend
from .utils.backends import (
    docker_available,
    ssh_host_available,
    ssh_host_connectable,
    vagrant_installed,
)
from .utils.installers import get_packages_dir

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from .utils.backends import Backend


# =============================================================================
# CLI Options
# =============================================================================


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom CLI options for backend selection."""
    group = parser.getgroup("hop3", "Hop3 E2E test options")

    group.addoption(
        "--docker",
        action="store_true",
        default=False,
        help="Enable Docker backend",
    )
    group.addoption(
        "--ssh",
        action="store_true",
        default=False,
        help="Enable SSH backend (requires HOP3_TEST_HOST or --ssh-host)",
    )
    group.addoption(
        "--ssh-host",
        action="store",
        default=None,
        metavar="HOST",
        help="SSH host to test against (implies --ssh)",
    )
    group.addoption(
        "--vagrant",
        action="store_true",
        default=False,
        help="Enable Vagrant backend (slow, starts VMs)",
    )


def _get_ssh_host(config: pytest.Config) -> str | None:
    """Get SSH host from CLI option or environment variable."""
    # CLI option takes precedence
    cli_host = config.getoption("--ssh-host")
    if cli_host:
        return cli_host
    # Fall back to environment variable
    return ssh_host_available()


def _explicit_backends_requested(config: pytest.Config) -> bool:
    """Check if any explicit backend option was specified."""
    return (
        config.getoption("--docker")
        or config.getoption("--ssh")
        or config.getoption("--ssh-host") is not None
        or config.getoption("--vagrant")
    )


def get_enabled_backends(config: pytest.Config) -> list[str]:
    """Get list of enabled backends based on CLI options.

    If no backend options specified: defaults to docker + ssh (if configured).
    If any backend option specified: only those backends are enabled.
    """
    explicit = _explicit_backends_requested(config)

    backends = []

    # Docker
    if explicit:
        if config.getoption("--docker") and docker_available():
            backends.append("docker")
    # Default: enable if available
    elif docker_available():
        backends.append("docker")

    # SSH
    ssh_host = _get_ssh_host(config)
    if explicit:
        if (config.getoption("--ssh") or config.getoption("--ssh-host")) and ssh_host:
            # Store host in environment for backends to use
            os.environ["HOP3_TEST_HOST"] = ssh_host
            backends.append("ssh")
    # Default: enable if host is configured
    elif ssh_host:
        backends.append("ssh")

    # Vagrant (never default, always explicit)
    if config.getoption("--vagrant") and vagrant_installed():
        backends.append("vagrant")

    return backends


def get_enabled_systemd_backends(config: pytest.Config) -> list[str]:
    """Get list of enabled backends that support systemd."""
    explicit = _explicit_backends_requested(config)

    backends = []

    # Docker with systemd
    if explicit:
        if config.getoption("--docker") and docker_available():
            backends.append("docker-systemd")
    # Default: enable if available
    elif docker_available():
        backends.append("docker-systemd")

    # SSH (has systemd)
    ssh_host = _get_ssh_host(config)
    if explicit:
        if (config.getoption("--ssh") or config.getoption("--ssh-host")) and ssh_host:
            os.environ["HOP3_TEST_HOST"] = ssh_host
            backends.append("ssh")
    # Default: enable if host is configured
    elif ssh_host:
        backends.append("ssh")

    # Vagrant (has systemd, never default)
    if config.getoption("--vagrant") and vagrant_installed():
        backends.append("vagrant")

    return backends


def get_enabled_deploy_targets(config: pytest.Config) -> list[str]:
    """Get list of enabled deployment targets based on CLI options."""
    explicit = _explicit_backends_requested(config)

    targets = []

    # Docker
    if explicit:
        if config.getoption("--docker") and docker_available():
            targets.append("docker")
    elif docker_available():
        targets.append("docker")

    # SSH (check connectivity)
    ssh_host = _get_ssh_host(config)
    if explicit:
        if (config.getoption("--ssh") or config.getoption("--ssh-host")) and ssh_host:
            os.environ["HOP3_TEST_HOST"] = ssh_host
            if ssh_host_connectable():
                targets.append("ssh")
    elif ssh_host_connectable():
        targets.append("ssh")

    # Vagrant not supported for hop3-deploy

    return targets


# =============================================================================
# Dynamic Parametrization
# =============================================================================


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically parametrize fixtures based on CLI options."""
    if "backend" in metafunc.fixturenames:
        backends = get_enabled_backends(metafunc.config)
        if not backends:
            pytest.skip("No backends available")
        metafunc.parametrize("backend", backends, indirect=True, scope="module")

    if "systemd_backend" in metafunc.fixturenames:
        backends = get_enabled_systemd_backends(metafunc.config)
        if not backends:
            pytest.skip("No systemd backends available")
        metafunc.parametrize("systemd_backend", backends, indirect=True, scope="module")

    if "deploy_target" in metafunc.fixturenames:
        targets = get_enabled_deploy_targets(metafunc.config)
        if not targets:
            pytest.skip("No deploy targets available")
        metafunc.parametrize("deploy_target", targets, scope="module")


# =============================================================================
# Backend Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def backend(request: pytest.FixtureRequest) -> Generator[Backend]:
    """Provide a test backend (Docker, SSH, or Vagrant).

    This fixture is dynamically parametrized based on CLI options.
    Tests using this fixture will run once per enabled backend.
    """
    backend_type = request.param
    backend_instance = get_backend(backend_type)

    if not backend_instance.setup():
        pytest.skip(f"Failed to setup {backend_type} backend")

    yield backend_instance

    backend_instance.teardown()


@pytest.fixture(scope="module")
def systemd_backend(request: pytest.FixtureRequest) -> Generator[Backend]:
    """Provide a test backend with systemd support.

    This fixture is dynamically parametrized based on CLI options.
    Backends with systemd support:
    - docker-systemd: Docker with systemd image
    - ssh: Remote SSH hosts (typically have systemd)
    - vagrant: Vagrant VMs (have systemd)

    Use this fixture for tests that require systemd (service tests).
    """
    backend_type = request.param
    backend_instance = get_backend(backend_type)

    if not backend_instance.setup():
        pytest.skip(f"Failed to setup {backend_type} backend")

    yield backend_instance

    backend_instance.teardown()


# =============================================================================
# Installer Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def bundled_installers(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Generate bundled installer scripts."""
    out_dir = tmp_path_factory.mktemp("installers")
    return bundle_installers(out_dir)


@pytest.fixture(scope="module")
def hop3_packages_dir() -> Path:
    """Get the path to the hop3 packages directory."""
    packages_dir = get_packages_dir()
    if not packages_dir.exists():
        pytest.fail(f"Packages directory not found: {packages_dir}")
    return packages_dir
