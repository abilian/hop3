# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Backend utilities for E2E tests.

This module provides access to the testing backends (Docker, SSH, Vagrant)
and utilities for discovering available backends based on environment.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

from hop3_installer.testing.backends import (
    Backend,
    DockerBackend,
    DockerSystemdBackend,
    SSHBackend,
    VagrantBackend,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "Backend",
    "available_backends",
    "available_systemd_backends",
    "docker_available",
    "docker_systemd_image_exists",
    "get_backend",
    "ssh_host_available",
    "ssh_host_connectable",
    "ssh_raw_host",
    "vagrant_installed",
]


def docker_available() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def docker_systemd_image_exists() -> bool:
    """Check if the hop3-test-systemd image exists.

    This image is required for systemd tests on Docker.
    """
    if not docker_available():
        return False

    try:
        result = subprocess.run(
            ["docker", "images", "-q", "hop3-test-systemd:latest"],
            check=False,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())
    except FileNotFoundError:
        return False


def ssh_host_available() -> str | None:
    """Get SSH host from environment if available.

    Uses HOP3_TEST_HOST for the hostname and HOP3_SSH_USER for the user
    (defaults to root). If HOP3_TEST_HOST already contains @, it's used as-is.

    Returns:
        SSH host string (user@host) or None if not configured.
    """
    host = os.environ.get("HOP3_TEST_HOST")
    if not host:
        return None

    # If host already has user@, return as-is
    if "@" in host:
        return host

    # Otherwise, prepend user from HOP3_SSH_USER (default: root)
    user = os.environ.get("HOP3_SSH_USER", "root")
    return f"{user}@{host}"


def ssh_raw_host() -> str | None:
    """Get raw SSH hostname from environment (without user prefix).

    Returns just the hostname part of HOP3_TEST_HOST, stripping any user@ prefix.
    Use this for commands like hop3-deploy that handle users internally.

    Returns:
        Raw hostname or None if not configured.
    """
    host = os.environ.get("HOP3_TEST_HOST")
    if not host:
        return None

    # Strip user@ prefix if present
    if "@" in host:
        return host.split("@", 1)[1]
    return host


def ssh_host_connectable() -> str | None:
    """Get SSH host from environment if available AND connectable.

    Returns:
        SSH host string (user@host) or None if not configured or not connectable.
    """
    host = ssh_host_available()
    if not host:
        return None

    # Try to connect with a simple command
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "StrictHostKeyChecking=accept-new",
                host,
                "true",
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return host
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def vagrant_installed() -> bool:
    """Check if Vagrant is installed.

    Note: This only checks if the vagrant binary is available.
    Vagrant tests are slow (start/stop VMs) so they require explicit opt-in
    via the --vagrant CLI flag. The opt-in check is handled in conftest.py.
    """
    try:
        result = subprocess.run(
            ["vagrant", "--version"],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def available_backends() -> list[str]:
    """Get list of available backend names (excluding Vagrant).

    Vagrant is excluded because it requires explicit opt-in via --vagrant flag.

    Returns:
        List of backend names that can be used for testing.
    """
    backends = []

    if docker_available():
        backends.append("docker")

    if ssh_host_available():
        backends.append("ssh")

    # Note: Vagrant excluded - requires explicit --vagrant flag

    return backends


def available_systemd_backends() -> list[str]:
    """Get list of available backends that support systemd (excluding Vagrant).

    Vagrant is excluded because it requires explicit opt-in via --vagrant flag.

    Returns:
        List of backend names with systemd support.
    """
    backends = []

    # Docker with systemd image (can auto-build if missing)
    if docker_available():
        backends.append("docker-systemd")

    # SSH hosts typically have systemd
    if ssh_host_available():
        backends.append("ssh")

    # Note: Vagrant excluded - requires explicit --vagrant flag

    return backends


def get_backend(
    backend_type: str,
    *,
    distro: str = "ubuntu",
    installer_dir: Path | None = None,
) -> Backend:
    """Create a backend instance by type.

    Args:
        backend_type: One of "docker", "docker-systemd", "ssh", "vagrant"
        distro: Distribution for Docker/Vagrant backends
        installer_dir: Path to installer directory (for Docker mount)

    Returns:
        Backend instance

    Raises:
        ValueError: If backend_type is unknown or unavailable
    """
    if backend_type == "docker":
        if not docker_available():
            msg = "Docker is not available"
            raise ValueError(msg)
        return DockerBackend(distro=distro, installer_dir=installer_dir)

    if backend_type == "docker-systemd":
        if not docker_available():
            msg = "Docker is not available"
            raise ValueError(msg)
        return DockerSystemdBackend(installer_dir=installer_dir)

    if backend_type == "ssh":
        host = ssh_host_available()
        if not host:
            msg = "HOP3_TEST_HOST environment variable not set"
            raise ValueError(msg)
        return SSHBackend(host=host)

    if backend_type == "vagrant":
        if not vagrant_installed():
            msg = "Vagrant is not installed"
            raise ValueError(msg)
        return VagrantBackend(vm_name=distro)

    msg = f"Unknown backend type: {backend_type}"
    raise ValueError(msg)
