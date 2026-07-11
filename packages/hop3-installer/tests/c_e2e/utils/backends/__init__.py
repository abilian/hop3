# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Test backends for E2E installer testing.

This package provides backend implementations for running installer tests
on different targets (Docker, SSH, Vagrant) and utilities for discovering
available backends.
"""

from __future__ import annotations

from .base import Backend
from .discovery import (
    available_backends,
    available_systemd_backends,
    docker_available,
    docker_systemd_image_exists,
    get_backend,
    set_ssh_host,
    ssh_host_available,
    ssh_host_connectable,
    ssh_raw_host,
    vagrant_installed,
)
from .docker import DockerBackend
from .docker_systemd import DockerSystemdBackend
from .ssh import SSHBackend
from .vagrant import VagrantBackend

__all__ = [
    # Backend classes
    "Backend",
    "DockerBackend",
    "DockerSystemdBackend",
    "SSHBackend",
    "VagrantBackend",
    # Discovery functions
    "available_backends",
    "available_systemd_backends",
    "docker_available",
    "docker_systemd_image_exists",
    "get_backend",
    "set_ssh_host",
    "ssh_host_available",
    "ssh_host_connectable",
    "ssh_raw_host",
    "vagrant_installed",
]
