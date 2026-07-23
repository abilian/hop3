# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Docker utility functions for server installer.

Shared utilities for configuring database services to work with Docker.
"""

from __future__ import annotations

import re

from hop3_installer.common import run_cmd


def get_docker_bridge_ip() -> str | None:
    """
    Get the Docker bridge network IP (usually 172.17.0.1).

    This is used by database services (PostgreSQL, MySQL, Redis) to configure
    bind addresses and access rules for Docker container connections.

    Returns:
        Docker bridge IP if available, None otherwise.
    """
    result = run_cmd(
        ["ip", "addr", "show", "docker0"],
        check=False,
    )
    if result.returncode != 0:
        return None

    # Parse output for inet address: "inet 172.17.0.1/16 ..."
    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", result.stdout)
    if match:
        return match.group(1)
    return None
