# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo execution backends."""

from __future__ import annotations

from .base import CommandResult, DemoBackend
from .docker import DockerDemoBackend
from .ssh import SSHDemoBackend

__all__ = [
    "CommandResult",
    "DemoBackend",
    "DockerDemoBackend",
    "SSHDemoBackend",
]


def create_backend(backend_type: str, config: dict) -> DemoBackend:
    """Create a demo backend based on type.

    Args:
        backend_type: Either 'ssh' or 'docker'
        config: Backend configuration

    Returns:
        Configured DemoBackend instance
    """
    if backend_type == "docker":
        return DockerDemoBackend(
            container_name=config.get("container_name", "hop3-demo"),
            image=config.get("image", "ubuntu:24.04"),
            project_root=config.get("project_root"),
        )
    if backend_type == "ssh":
        return SSHDemoBackend(
            host=config["host"],
            user=config.get("user", "root"),
        )
    msg = f"Unknown backend type: {backend_type}"
    raise ValueError(msg)
