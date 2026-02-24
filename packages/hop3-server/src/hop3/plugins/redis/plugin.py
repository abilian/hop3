# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Redis plugin for Hop3."""

from __future__ import annotations

import logging

from dishka import Provider, Scope, provide

from hop3.core.hooks import hookimpl
from hop3.core.protocols import HealthCheckResult

from . import cli
from .factory import RedisClientFactory
from .redis import RedisAddon

assert cli

logger = logging.getLogger(__name__)

# Check if redis package is available
_REDIS_AVAILABLE = False
try:
    import redis

    _REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore[assignment,unused-ignore]


class RedisHealthCheck:
    """Health check for Redis connectivity."""

    name = "redis"

    def is_configured(self) -> bool:
        """Check if Redis package is available.

        Redis doesn't require explicit configuration - it just needs to be running.
        """
        return _REDIS_AVAILABLE

    def check(self) -> HealthCheckResult:
        """Test Redis connectivity."""
        if not _REDIS_AVAILABLE:
            return HealthCheckResult(
                name="Redis",
                passed=True,
                message="Redis package not installed (skipped)",
            )

        try:
            factory = RedisClientFactory.from_config()
            client = redis.Redis(**factory.get_connection_params())
            info = client.info()

            return HealthCheckResult(
                name="Redis",
                passed=True,
                message="Connection successful",
                details={
                    "version": info.get("redis_version", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                },
            )

        except redis.ConnectionError as e:
            return HealthCheckResult(
                name="Redis",
                passed=True,  # Redis is optional, connection failure is OK
                message=f"Not accessible: {e}",
            )
        except Exception as e:
            return HealthCheckResult(
                name="Redis",
                passed=True,  # Redis is optional
                message=f"Health check error: {e}",
            )


class RedisPlugin:
    """Redis addon plugin for Hop3."""

    name = "redis"

    @hookimpl
    def get_addons(self) -> list:
        """Return Redis addon implementation."""
        return [RedisAddon]

    @hookimpl
    def get_health_checks(self) -> list:
        """Return Redis health check."""
        return [RedisHealthCheck()]


class RedisPluginProvider(Provider):
    """DI provider for Redis addon infrastructure.

    Provides RedisClientFactory for centralized Redis configuration
    and connection management.

    Configuration is read from environment variables with REDIS_ prefix.
    """

    scope = Scope.APP

    @provide
    def get_redis_factory(self) -> RedisClientFactory:
        """Provide Redis client factory.

        Returns:
            RedisClientFactory instance configured from REDIS_* environment variables
        """
        return RedisClientFactory.from_config()


@hookimpl
def get_di_providers() -> list:
    """Register Redis DI providers.

    This hook is called by the DI container during initialization
    to collect providers from all plugins.

    Returns:
        List containing RedisPluginProvider instance
    """
    return [RedisPluginProvider()]


# Auto-register plugin instance when module is imported
plugin = RedisPlugin()
