# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RedisAddon:
    """Redis service addon for Hop3 applications."""

    app_name: str
    settings: dict

    def create(self) -> None:
        """Create Redis instance configuration if needed."""
        # Redis doesn't require database creation like PostgreSQL
        # Configuration would be handled by Redis instance provisioning
        pass

    @property
    def instance_name(self) -> str:
        """Get the Redis instance name for this app."""
        return f"{self.app_name}_redis"

    @property
    def port(self) -> int:
        """Get the Redis port (could be app-specific or shared)."""
        # Default Redis port, could be customized per app
        return self.settings.get("redis_port", 6379)

    def get_env(self) -> dict[str, str]:
        """Construct the environment variables for Redis connection.

        Returns:
            A dictionary with the environment variable 'REDIS_URL' pointing to the Redis connection string.
        """
        host = self.settings.get("redis_host", "localhost")
        port = self.port
        password = self.settings.get("redis_password", "")

        if password:
            redis_url = f"redis://:{password}@{host}:{port}/0"
        else:
            redis_url = f"redis://{host}:{port}/0"

        return {
            "REDIS_URL": redis_url,
        }
