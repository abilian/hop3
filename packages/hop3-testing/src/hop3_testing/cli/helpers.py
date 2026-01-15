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

if TYPE_CHECKING:
    from hop3_testing.targets.base import DeploymentTarget


def create_target(target_type: str, host: str | None) -> DeploymentTarget:
    """Create a deployment target (simple version)."""
    return create_target_with_options(target_type=target_type, host=host)


def create_target_with_options(
    target_type: str,
    host: str | None = None,
    port: int = 22,
    user: str = "hop3",
    ssh_key: str | None = None,
    use_cache: bool = False,
    force_rebuild: bool = False,
) -> DeploymentTarget:
    """Create a deployment target with full options."""
    if target_type == "docker":
        return DockerTarget({
            "rebuild": not use_cache,
            "use_cache": use_cache,
            "force_rebuild": force_rebuild,
        })
    if target_type == "remote":
        # Get host from args or environment
        actual_host = host or os.getenv("HOP3_TEST_HOST")
        if not actual_host:
            click.echo(
                "--host required for remote target (or set HOP3_TEST_HOST)", err=True
            )
            sys.exit(1)

        return RemoteTarget({
            "host": actual_host,
            "port": port,
            "user": user,
            "ssh_key": ssh_key or os.getenv("HOP3_TEST_SSH_KEY"),
        })
    click.echo(f"Unknown target type: {target_type}", err=True)
    sys.exit(1)
