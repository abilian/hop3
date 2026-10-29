# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Redis plugin for Hop3."""

from __future__ import annotations

import logging
from typing import Any, cast

import redis
from dishka import Provider, Scope, provide

from hop3.core.hooks import hookimpl
from hop3.core.protocols import HealthCheckResult

from . import cli
from .factory import RedisClientFactory
from .redis import RedisAddon

assert cli

logger = logging.getLogger(__name__)


class RedisHealthCheck:
    """Health check for Redis connectivity."""

    name = "redis"

    def check(self) -> HealthCheckResult:
        """
        Test Redis connectivity.

        Redis is an optional addon: when it's unreachable, we return
        ``passed=False, severity="warn"``
        so the operator sees ⚠ (not ✓) in ``hop3 system status`` and the
        overall summary counts it as a warning rather than a hard failure.
        """
        try:
            factory = RedisClientFactory.from_config()
            client = redis.Redis(**factory.get_connection_params())
            info = cast("dict[str, Any]", client.info())

            return HealthCheckResult(
                name="Redis",
                passed=True,
                message="Connection successful",
                details={
                    "version": info.get("redis_version", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                },
            )

        except Exception as e:
            # redis.ConnectionError, AuthenticationError, etc. Redis is
            # optional → warn (not fail) so the server stays "OK overall"
            # even when redis is intentionally not running.
            return HealthCheckResult(
                name="Redis",
                passed=False,
                severity="warn",
                message=f"unreachable — {e}",
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

    @hookimpl
    def cli_commands(self) -> list:
        """Contribute `addon redis <verb>` commands to the CLI."""
        return cli.COMMANDS


class RedisPluginProvider(Provider):
    """
    DI provider for Redis addon infrastructure.

    Provides RedisClientFactory for centralized Redis configuration
    and connection management.

    Configuration is read from environment variables with REDIS_ prefix.
    """

    scope = Scope.APP

    @provide
    def get_redis_factory(self) -> RedisClientFactory:
        """
        Provide Redis client factory.

        Returns:
            RedisClientFactory instance configured from REDIS_* environment variables
        """
        return RedisClientFactory.from_config()


@hookimpl
def get_di_providers() -> list:
    """
    Register Redis DI providers.

    This hook is called by the DI container during initialization
    to collect providers from all plugins.

    Returns:
        List containing RedisPluginProvider instance
    """
    return [RedisPluginProvider()]


# Auto-register plugin instance when module is imported
plugin = RedisPlugin()
