# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Redis configuration."""

from __future__ import annotations

import re
from pathlib import Path

from hop3_installer.common import (
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

# Common Redis config file locations
REDIS_CONF_PATHS = [
    Path("/etc/redis/redis.conf"),
    Path("/etc/redis.conf"),
]


def _get_docker_bridge_ip() -> str | None:
    """Get the Docker bridge network IP (usually 172.17.0.1).

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


def _configure_redis_bind() -> None:
    """Configure Redis to bind to localhost and Docker bridge.

    This allows Docker containers to connect to Redis via host.docker.internal
    while keeping Redis inaccessible from external networks.
    """
    # Find Redis config file
    redis_conf = None
    for path in REDIS_CONF_PATHS:
        if path.exists():
            redis_conf = path
            break

    if not redis_conf:
        print_warning("Redis config file not found, skipping bind configuration")
        return

    # Get Docker bridge IP
    docker_ip = _get_docker_bridge_ip()
    if not docker_ip:
        print_detail("Docker bridge not found, Redis will bind to localhost only")
        return

    # Read current config
    content = redis_conf.read_text()

    # Check if already configured for Docker
    if docker_ip in content:
        print_detail(f"Redis already configured for Docker bridge ({docker_ip})")
        return

    # Update bind directive to include Docker bridge
    # Match lines like: bind 127.0.0.1 ::1
    # or: bind 127.0.0.1
    new_bind = f"bind 127.0.0.1 {docker_ip}"

    if re.search(r"^bind\s+", content, re.MULTILINE):
        # Replace existing bind directive
        content = re.sub(
            r"^bind\s+.*$",
            new_bind,
            content,
            flags=re.MULTILINE,
        )
        print_detail(f"Updated Redis bind to: {new_bind}")
    else:
        # Add bind directive if not present
        content = f"{new_bind}\n{content}"
        print_detail(f"Added Redis bind: {new_bind}")

    # Write updated config
    redis_conf.write_text(content)
    print_detail("Redis configured to accept connections from Docker containers")


def configure_redis() -> None:
    """Configure Redis for Hop3 use.

    Ensures Redis is:
    - Running as a primary (not a replica)
    - Bound to localhost and Docker bridge (for container access)
    - Enabled and started
    """
    print_info("Configuring Redis...")

    # Configure bind address for Docker access
    _configure_redis_bind()

    # Ensure Redis is not configured as a replica
    # This fixes the "You can't write against a read only replica" error
    result = run_cmd(
        ["redis-cli", "CONFIG", "SET", "replica-read-only", "no"],
        check=False,
    )
    if result.returncode != 0:
        print_warning(
            "Could not set replica-read-only=no (Redis may not be running yet)"
        )

    # Remove any replicaof configuration (make this a primary)
    result = run_cmd(
        ["redis-cli", "REPLICAOF", "NO", "ONE"],
        check=False,
    )
    if result.returncode == 0:
        print_detail("Redis configured as primary (not replica)")

    # Enable and restart Redis service (restart to apply bind changes)
    run_cmd(["systemctl", "enable", "redis-server"], check=False)
    run_cmd(["systemctl", "restart", "redis-server"], check=False)

    # Verify Redis is working
    result = run_cmd(["redis-cli", "PING"], check=False)
    if result.returncode == 0 and "PONG" in result.stdout:
        print_success("Redis configured and running")
    else:
        print_warning("Redis may not be running correctly")
