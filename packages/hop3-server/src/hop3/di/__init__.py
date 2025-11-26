# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dependency injection infrastructure using Dishka.

Usage:
    # For web endpoints (Litestar)
    from dishka.integrations.litestar import FromDishka, inject

    @inject
    async def my_view(service: FromDishka[MyService]):
        ...

    # For CLI/deployment contexts
    from hop3.di import create_container

    container = create_container()
    try:
        service = container.get(MyService)
        service.do_work()
    finally:
        container.close()
"""

from __future__ import annotations

from .container import create_async_container, create_container
from .providers import ConfigProvider, HopCoreProvider

__all__ = [
    "ConfigProvider",
    "HopCoreProvider",
    "create_async_container",
    "create_container",
]
