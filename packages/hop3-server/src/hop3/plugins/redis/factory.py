# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Redis client factory for dependency injection.

This module provides a RedisClientFactory service that manages Redis
connection configuration and can be injected via Dishka DI.
"""

from __future__ import annotations

from dataclasses import dataclass

from hop3.config import HopConfig


@dataclass(frozen=True)
class RedisClientFactory:
    """Redis client factory service.

    This service provides centralized configuration for Redis
    connections and operations. It's designed to be injected via
    Dishka DI for easier testing and configuration management.

    This is a lightweight service that provides connection parameters.
    The actual Redis operations are handled by RedisAddon instances,
    which can use this factory for connection details.

    Attributes:
        host: Redis server host
        port: Redis server port
        password: Redis password (optional)
        max_connections: Maximum connections in pool
    """

    host: str
    port: int
    password: str | None = None
    max_connections: int = 50

    @classmethod
    def from_config(cls, config: HopConfig) -> RedisClientFactory:
        """Create RedisClientFactory from application configuration.

        Args:
            config: Application configuration

        Returns:
            RedisClientFactory instance configured from HopConfig
        """
        return cls(
            host=config.redis_host,
            port=config.redis_port,
            password=config.redis_password,
            max_connections=config.redis_max_connections,
        )

    def get_connection_params(self, db: int = 0) -> dict[str, any]:
        """Get connection parameters for redis-py.

        Args:
            db: Redis database number (defaults to 0)

        Returns:
            Dictionary with connection parameters for redis.Redis()
        """
        params = {
            "host": self.host,
            "port": self.port,
            "db": db,
            "decode_responses": True,
            "max_connections": self.max_connections,
        }

        if self.password:
            params["password"] = self.password

        return params

    def get_url(self, db: int = 0, include_password: bool = False) -> str:
        """Get Redis connection URL.

        Args:
            db: Redis database number
            include_password: Whether to include password in URL

        Returns:
            Redis connection URL string
        """
        if include_password and self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{db}"
        return f"redis://{self.host}:{self.port}/{db}"
