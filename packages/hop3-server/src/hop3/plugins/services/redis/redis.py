# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Redis service implementation.

This module implements the ServiceStrategy protocol for Redis,
allowing applications to create, attach, and manage Redis instances.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RedisService:
    """Redis service implementation using ServiceStrategy protocol.

    This service manages Redis instances. Each service instance
    creates a dedicated Redis database (using Redis database numbers 0-15).

    Attributes:
        service_name: The unique name for this Redis service instance
    """

    # Class attribute for the strategy name
    name: str = "redis"

    # Instance attribute
    service_name: str = ""

    def __post_init__(self):
        """Validate that service_name is provided."""
        if not self.service_name:
            msg = "service_name is required for RedisService"
            raise ValueError(msg)

    @property
    def redis_url(self) -> str:
        """Redis connection URL for this service instance.

        Returns a connection URL in the format:
        redis://localhost:6379/0
        """
        # TODO: Support password-protected Redis instances
        # For now, assume Redis is running on localhost without password
        return f"redis://localhost:6379/{self.db_number}"

    @property
    def db_number(self) -> int:
        """Redis database number (0-15).

        We hash the service name to get a consistent database number.
        """
        # Use hash of service name to get a number between 0-15
        return hash(self.service_name) % 16

    def create(self) -> None:
        """Create a new Redis service instance.

        For Redis, there's no database creation like PostgreSQL.
        We just ensure Redis is running and the database number is valid.
        This method is idempotent.
        """
        # Check if Redis is running
        try:
            result = subprocess.run(
                ["redis-cli", "ping"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode != 0 or result.stdout.strip() != "PONG":
                msg = "Redis is not running or not accessible"
                raise RuntimeError(msg)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            msg = f"Failed to connect to Redis: {e}"
            raise RuntimeError(msg) from e

        # Redis databases (0-15) exist by default, no creation needed

    def destroy(self) -> None:
        """Destroy the Redis service instance.

        This flushes all data from the assigned database number.
        """
        try:
            subprocess.run(
                ["redis-cli", "-n", str(self.db_number), "FLUSHDB"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
        except subprocess.CalledProcessError as e:
            msg = f"Failed to flush Redis database {self.db_number}: {e}"
            raise RuntimeError(msg) from e

    def get_connection_details(self) -> dict[str, Any]:
        """Get connection details for this Redis service.

        Returns:
            Dictionary containing connection information including:
            - url: Redis connection URL
            - host: Redis host
            - port: Redis port
            - db: Database number
        """
        return {
            "url": self.redis_url,
            "host": "localhost",
            "port": 6379,
            "db": self.db_number,
            "service_name": self.service_name,
        }

    def info(self) -> dict[str, Any]:
        """Get information about this Redis service.

        Returns:
            Dictionary containing service information
        """
        try:
            # Get Redis INFO for this database
            result = subprocess.run(
                ["redis-cli", "-n", str(self.db_number), "INFO", "keyspace"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )

            # Get number of keys
            keys_result = subprocess.run(
                ["redis-cli", "-n", str(self.db_number), "DBSIZE"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )

            num_keys = int(keys_result.stdout.strip())

            return {
                "service_name": self.service_name,
                "type": "redis",
                "url": self.redis_url,
                "db_number": self.db_number,
                "num_keys": num_keys,
                "status": "available",
            }
        except (subprocess.CalledProcessError, ValueError) as e:
            return {
                "service_name": self.service_name,
                "type": "redis",
                "status": "error",
                "error": str(e),
            }

    def backup(self, backup_path: Path) -> None:
        """Create a backup of the Redis database.

        Args:
            backup_path: Path where the backup should be stored
        """
        # Use SAVE to create a dump.rdb file, then copy it
        try:
            # Trigger a save
            subprocess.run(
                ["redis-cli", "SAVE"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            # Get the Redis data directory (usually /var/lib/redis or /var/redis)
            # For now, assume dump.rdb is in a known location
            # This is simplified - production would need to find the actual location
            msg = "Redis backup functionality requires configuration"
            raise NotImplementedError(msg)

        except subprocess.CalledProcessError as e:
            msg = f"Failed to backup Redis: {e}"
            raise RuntimeError(msg) from e

    def restore(self, backup_path: Path) -> None:
        """Restore the Redis database from a backup.

        Args:
            backup_path: Path to the backup file
        """
        msg = "Redis restore functionality requires configuration"
        raise NotImplementedError(msg)
