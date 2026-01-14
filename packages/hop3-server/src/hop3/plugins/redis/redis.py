# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Redis service implementation.

This module implements the Addon protocol for Redis,
allowing applications to attach to a Redis instance.

Unlike PostgreSQL, Redis doesn't require per-addon database creation.
Each addon gets a dedicated database number (0-15) for isolation.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hop3.config import HOP3_ROOT


@dataclass(frozen=True)
class RedisAddon:
    """Redis service implementation using Addon protocol.

    This service provides Redis access to applications. Each addon instance
    uses a dedicated Redis database number for isolation.

    Attributes:
        addon_name: The unique name for this Redis service instance
        _db_number: The Redis database number (0-15) for this instance
    """

    # Class attribute for the strategy name
    name: str = "redis"

    # Instance attributes
    addon_name: str = ""
    _db_number: int = 0  # Default to database 0

    def __post_init__(self):
        """Validate that addon_name is provided."""
        if not self.addon_name:
            msg = "addon_name is required for RedisAddon"
            raise ValueError(msg)

        # Assign a database number based on addon name hash (0-15)
        # This provides consistent assignment for the same addon name
        if self._db_number == 0:
            db_num = hash(self.addon_name) % 16
            object.__setattr__(self, "_db_number", db_num)

    @property
    def db_number(self) -> int:
        """Get the Redis database number for this addon."""
        return self._db_number

    @property
    def instance_name(self) -> str:
        """Get a sanitized instance name."""
        return self.addon_name.replace("-", "_")

    def create(self) -> None:
        """Initialize the Redis database for this addon.

        Redis databases (0-15) always exist, so this just verifies
        Redis is accessible and optionally clears the database.
        """
        # Verify Redis is accessible
        cmd = ["redis-cli", "ping"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0 or result.stdout.strip() != "PONG":
            msg = f"Redis is not accessible: {result.stderr or 'no response'}"
            raise RuntimeError(msg)

        # Ensure Redis is configured as a primary (not a read-only replica)
        # This fixes "You can't write against a read only replica" errors
        self._ensure_writable()

        # Select the database and set a marker key to indicate it's in use
        marker_cmd = [
            "redis-cli",
            "-n",
            str(self.db_number),
            "SET",
            f"hop3:addon:{self.addon_name}:created",
            datetime.now(timezone.utc).isoformat(),
        ]
        result = subprocess.run(marker_cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            # Check if this is a read-only replica error
            if "read only replica" in result.stderr.lower():
                msg = (
                    "Redis is configured as a read-only replica. "
                    "Run 'redis-cli REPLICAOF NO ONE' to make it a primary, "
                    "or re-run the Hop3 installer with --features=redis"
                )
            else:
                msg = f"Failed to initialize Redis database: {result.stderr}"
            raise RuntimeError(msg)

    def _ensure_writable(self) -> None:
        """Ensure Redis is writable (not a read-only replica).

        If Redis is configured as a replica, attempt to make it a primary.
        """
        # Check if Redis is a replica
        result = subprocess.run(
            ["redis-cli", "INFO", "replication"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return  # Can't check, assume it's fine

        # Check if role is slave/replica
        if "role:slave" in result.stdout:
            # Try to make it a primary
            subprocess.run(
                ["redis-cli", "REPLICAOF", "NO", "ONE"],
                capture_output=True,
                text=True,
                check=False,
            )
            # Also allow writes on replica (fallback if REPLICAOF fails)
            subprocess.run(
                ["redis-cli", "CONFIG", "SET", "replica-read-only", "no"],
                capture_output=True,
                text=True,
                check=False,
            )

    def destroy(self) -> None:
        """Clear all data in the Redis database for this addon.

        This flushes all keys in the assigned database number.
        """
        cmd = ["redis-cli", "-n", str(self.db_number), "FLUSHDB"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            msg = f"Failed to flush Redis database {self.db_number}: {result.stderr}"
            raise RuntimeError(msg)

    def get_connection_details(self) -> dict[str, str]:
        """Get environment variables for connecting to this Redis instance.

        Returns:
            Dictionary with REDIS_URL and other connection parameters

        Note: This always returns localhost as the host. For Docker deployments,
        the Docker deployer transforms localhost → host.docker.internal when
        generating docker-compose.yml. This ensures native apps work correctly
        while Docker apps get the right host after transformation.
        """
        # Always use localhost - Docker deployer transforms this for containers
        host = "localhost"
        port = "6379"

        return {
            "REDIS_URL": f"redis://{host}:{port}/{self.db_number}",
            "REDIS_HOST": host,
            "REDIS_PORT": port,
            "REDIS_DB": str(self.db_number),
        }

    def backup(self) -> Path:
        """Create a backup of the Redis database.

        Uses redis-cli to dump all keys in this database.

        Returns:
            Path to the backup file
        """
        backup_dir = HOP3_ROOT / "backups" / "redis"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{self.addon_name}_{timestamp}.json"

        # Get all keys in this database
        keys_cmd = ["redis-cli", "-n", str(self.db_number), "KEYS", "*"]
        result = subprocess.run(keys_cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            msg = f"Failed to list Redis keys: {result.stderr}"
            raise RuntimeError(msg)

        keys = result.stdout.strip().split("\n") if result.stdout.strip() else []

        # Dump each key with its type and value
        keys_data: dict[str, dict[str, Any]] = {}
        backup_data: dict[str, Any] = {
            "addon_name": self.addon_name,
            "db_number": self.db_number,
            "timestamp": timestamp,
            "keys": keys_data,
        }

        for key in keys:
            if not key:
                continue

            # Get key type
            type_cmd = ["redis-cli", "-n", str(self.db_number), "TYPE", key]
            type_result = subprocess.run(
                type_cmd, capture_output=True, text=True, check=False
            )
            key_type = type_result.stdout.strip()

            # Get value based on type
            if key_type == "string":
                get_cmd = ["redis-cli", "-n", str(self.db_number), "GET", key]
                value_result = subprocess.run(
                    get_cmd, capture_output=True, text=True, check=False
                )
                keys_data[key] = {
                    "type": "string",
                    "value": value_result.stdout.strip(),
                }
            elif key_type == "list":
                get_cmd = [
                    "redis-cli",
                    "-n",
                    str(self.db_number),
                    "LRANGE",
                    key,
                    "0",
                    "-1",
                ]
                value_result = subprocess.run(
                    get_cmd, capture_output=True, text=True, check=False
                )
                keys_data[key] = {
                    "type": "list",
                    "value": value_result.stdout.strip().split("\n"),
                }
            elif key_type == "set":
                get_cmd = ["redis-cli", "-n", str(self.db_number), "SMEMBERS", key]
                value_result = subprocess.run(
                    get_cmd, capture_output=True, text=True, check=False
                )
                keys_data[key] = {
                    "type": "set",
                    "value": value_result.stdout.strip().split("\n"),
                }
            elif key_type == "hash":
                get_cmd = ["redis-cli", "-n", str(self.db_number), "HGETALL", key]
                value_result = subprocess.run(
                    get_cmd, capture_output=True, text=True, check=False
                )
                # Parse alternating key/value pairs
                items = value_result.stdout.strip().split("\n")
                hash_dict = {}
                for i in range(0, len(items) - 1, 2):
                    hash_dict[items[i]] = items[i + 1]
                keys_data[key] = {"type": "hash", "value": hash_dict}
            # Skip other types for now (zset, stream, etc.)

        # Write backup to file
        with Path(backup_file).open("w") as f:
            json.dump(backup_data, f, indent=2)

        return backup_file

    def restore(self, backup_path: Path) -> None:
        """Restore Redis database from a backup file.

        Args:
            backup_path: Path to the JSON backup file
        """
        if not backup_path.exists():
            msg = f"Backup file not found: {backup_path}"
            raise FileNotFoundError(msg)

        with Path(backup_path).open() as f:
            backup_data = json.load(f)

        # Restore each key based on its type
        for key, data in backup_data.get("keys", {}).items():
            key_type = data["type"]
            value = data["value"]

            if key_type == "string":
                cmd = [
                    "redis-cli",
                    "-n",
                    str(self.db_number),
                    "SET",
                    key,
                    str(value),
                ]
                subprocess.run(cmd, capture_output=True, text=True, check=False)
            elif key_type == "list":
                # Delete existing key first
                subprocess.run(
                    ["redis-cli", "-n", str(self.db_number), "DEL", key],
                    capture_output=True,
                    check=False,
                )
                for item in value:
                    cmd = [
                        "redis-cli",
                        "-n",
                        str(self.db_number),
                        "RPUSH",
                        key,
                        str(item),
                    ]
                    subprocess.run(cmd, capture_output=True, text=True, check=False)
            elif key_type == "set":
                subprocess.run(
                    ["redis-cli", "-n", str(self.db_number), "DEL", key],
                    capture_output=True,
                    check=False,
                )
                for item in value:
                    cmd = [
                        "redis-cli",
                        "-n",
                        str(self.db_number),
                        "SADD",
                        key,
                        str(item),
                    ]
                    subprocess.run(cmd, capture_output=True, text=True, check=False)
            elif key_type == "hash":
                subprocess.run(
                    ["redis-cli", "-n", str(self.db_number), "DEL", key],
                    capture_output=True,
                    check=False,
                )
                for field, val in value.items():
                    cmd = [
                        "redis-cli",
                        "-n",
                        str(self.db_number),
                        "HSET",
                        key,
                        field,
                        str(val),
                    ]
                    subprocess.run(cmd, capture_output=True, text=True, check=False)

    def info(self) -> dict[str, Any]:
        """Get information about the Redis service.

        Returns:
            Dictionary with service details
        """
        # Get Redis server info
        info_cmd = ["redis-cli", "INFO", "server"]
        result = subprocess.run(info_cmd, capture_output=True, text=True, check=False)

        version = "unknown"
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("redis_version:"):
                    version = line.split(":")[1].strip()
                    break

        # Get number of keys in this database
        dbsize_cmd = ["redis-cli", "-n", str(self.db_number), "DBSIZE"]
        dbsize_result = subprocess.run(
            dbsize_cmd, capture_output=True, text=True, check=False
        )
        key_count = 0
        if dbsize_result.returncode == 0:
            # Output format: "(integer) N"
            with contextlib.suppress(ValueError, IndexError):
                key_count = int(dbsize_result.stdout.strip())

        # Get memory usage for this database (approximate)
        memory_cmd = ["redis-cli", "-n", str(self.db_number), "INFO", "memory"]
        memory_result = subprocess.run(
            memory_cmd, capture_output=True, text=True, check=False
        )
        used_memory = "unknown"
        if memory_result.returncode == 0:
            for line in memory_result.stdout.split("\n"):
                if line.startswith("used_memory_human:"):
                    used_memory = line.split(":")[1].strip()
                    break

        return {
            "addon_name": self.addon_name,
            "type": "redis",
            "host": "localhost",
            "port": 6379,
            "database": self.db_number,
            "key_count": key_count,
            "version": version,
            "memory_used": used_memory,
        }
