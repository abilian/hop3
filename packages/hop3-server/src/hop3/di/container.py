# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Container creation for Hop3.

This module provides container creation for Dishka dependency injection.
The container lifecycle is managed by:
- Starlette integration for web requests (via setup_dishka)
- Explicit creation for CLI/deployment contexts
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import make_async_container, make_container

from .providers import ConfigProvider, HopServicesProvider

if TYPE_CHECKING:
    from dishka import AsyncContainer, Container


def create_container() -> Container:
    """Create a new synchronous application container.

    This creates a fresh container with all providers registered.
    The container should be closed when no longer needed.

    Use this for CLI/deployment contexts where async is not needed.

    Returns:
        Container: Dishka container with all providers registered

    Example:
        # For CLI/deployment contexts
        container = create_container()
        try:
            service = container.get(MyService)
            service.do_work()
        finally:
            container.close()
    """
    return make_container(
        ConfigProvider(),
        HopServicesProvider(),
    )


def create_async_container() -> AsyncContainer:
    """Create a new asynchronous application container.

    This creates a fresh async container with all providers registered.
    Use this for web contexts with async views (Starlette, FastAPI).

    Returns:
        AsyncContainer: Dishka async container with all providers registered

    Example:
        # For web contexts, use setup_dishka() instead (see asgi.py)
        from dishka.integrations.starlette import setup_dishka

        container = create_async_container()
        setup_dishka(container, app=app)
    """
    return make_async_container(
        ConfigProvider(),
        HopServicesProvider(),
    )
