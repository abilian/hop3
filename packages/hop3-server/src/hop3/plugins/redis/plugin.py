# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Redis plugin for Hop3."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hop3.config import HopConfig
from hop3.core.hooks import hookimpl

from . import cli
from .factory import RedisClientFactory
from .redis import RedisAddon

assert cli


class RedisPlugin:
    """Redis service plugin for Hop3."""

    name = "redis"

    @hookimpl
    def get_service_strategies(self) -> list:
        """Return Redis service strategy."""
        return [RedisAddon]


class RedisPluginProvider(Provider):
    """DI provider for Redis services.

    Provides RedisClientFactory for centralized Redis configuration
    and connection management.
    """

    scope = Scope.APP

    @provide
    def get_redis_factory(self, config: HopConfig) -> RedisClientFactory:
        """Provide Redis client factory service.

        Dependencies:
            config: Application configuration (from ConfigProvider)

        Returns:
            RedisClientFactory instance configured from HopConfig
        """
        return RedisClientFactory.from_config(config)


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
