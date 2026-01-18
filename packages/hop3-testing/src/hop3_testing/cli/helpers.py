# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Helper functions for CLI target creation."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import click

from hop3_testing.targets import DockerTarget, RemoteTarget
from hop3_testing.targets.config import DockerConfig, RemoteConfig

if TYPE_CHECKING:
    from hop3_testing.targets.base import DeploymentTarget


def create_target(
    target_type: str, host: str | None, verbose: bool = False
) -> DeploymentTarget:
    """Create a deployment target (simple version)."""
    return create_target_with_options(
        target_type=target_type, host=host, verbose=verbose
    )


def create_target_with_options(
    target_type: str,
    host: str | None = None,
    port: int = 22,
    user: str = "hop3",
    ssh_key: str | None = None,
    use_cache: bool = False,
    force_rebuild: bool = False,
    verbose: bool = False,
) -> DeploymentTarget:
    """Create a deployment target with full options.

    This is a convenience function for simple use cases. For full control
    over target configuration, use DockerTarget or RemoteTarget directly
    with their respective config classes.

    Args:
        target_type: "docker" or "remote"
        host: Remote hostname (required for remote target)
        port: SSH port (default: 22)
        user: SSH user (default: "hop3")
        ssh_key: Path to SSH key
        use_cache: Skip rebuild if image exists
        force_rebuild: Force full rebuild (not used in new API)
        verbose: Verbose output

    Returns:
        Configured DeploymentTarget instance
    """
    if target_type == "docker":
        # Create Docker target with pre-built image (no deployment)
        docker_config = DockerConfig(
            image="hop3-ready:latest",
            container_name="hop3-test",
        )
        return DockerTarget(docker_config)

    if target_type == "remote":
        # Get host from args or environment
        actual_host = host or os.getenv("HOP3_TEST_HOST")
        if not actual_host:
            click.echo(
                "--host required for remote target (or set HOP3_TEST_HOST)", err=True
            )
            sys.exit(1)

        assert actual_host is not None  # Type narrowing after sys.exit
        remote_config = RemoteConfig(
            host=actual_host,
            port=port,
            user=user,
            ssh_key=ssh_key or os.getenv("HOP3_TEST_SSH_KEY"),
        )
        return RemoteTarget(remote_config)

    click.echo(f"Unknown target type: {target_type}", err=True)
    sys.exit(1)
