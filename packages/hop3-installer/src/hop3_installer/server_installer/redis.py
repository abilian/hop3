# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Redis configuration."""

from __future__ import annotations

from hop3_installer.common import (
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)


def configure_redis() -> None:
    """Configure Redis for Hop3 use.

    Ensures Redis is:
    - Running as a primary (not a replica)
    - Enabled and started
    - Accessible on localhost
    """
    print_info("Configuring Redis...")

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

    # Enable and start Redis service
    run_cmd(["systemctl", "enable", "redis-server"], check=False)
    run_cmd(["systemctl", "start", "redis-server"], check=False)

    # Verify Redis is working
    result = run_cmd(["redis-cli", "PING"], check=False)
    if result.returncode == 0 and "PONG" in result.stdout:
        print_success("Redis configured and running")
    else:
        print_warning("Redis may not be running correctly")
