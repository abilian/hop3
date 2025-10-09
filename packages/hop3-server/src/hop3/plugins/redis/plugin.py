# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Redis plugin for Hop3."""

from __future__ import annotations

from hop3.core.hooks import hookimpl

from . import cli
from .redis import RedisAddon

assert cli


class RedisPlugin:
    """Redis service plugin for Hop3."""

    name = "redis"

    @hookimpl
    def get_service_strategies(self) -> list:
        """Return Redis service strategy."""
        return [RedisAddon]


# Auto-register plugin instance when module is imported
plugin = RedisPlugin()
