# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Redis plugin for Hop3.

This plugin provides Redis service capabilities to Hop3 applications.
"""

from __future__ import annotations

from hop3.core.hooks import hop3_hook_impl
from hop3.core.protocols import ServiceStrategy

from . import cli
from .redis import RedisService

assert cli


class RedisPlugin:
    """Redis service plugin for Hop3.

    This plugin registers the Redis service strategy with the Hop3
    plugin system, allowing applications to create and attach Redis instances.
    """

    name = "redis"

    @hop3_hook_impl
    def get_service_strategies(self) -> list[type[ServiceStrategy]]:
        """Return Redis service strategy."""
        return [RedisService]
