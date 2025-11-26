# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Container creation for Hop3.

This module provides container creation for Dishka dependency injection.
The container lifecycle is managed by:
- Litestar integration for web requests (via setup_dishka)
- Explicit creation for CLI/deployment contexts

Plugin Integration:
- Plugins can contribute DI providers via the get_di_providers() hook
- Plugin providers are automatically collected and registered in containers
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import make_async_container, make_container

from .providers import ConfigProvider, DatabaseProvider, HopCoreProvider

if TYPE_CHECKING:
    from dishka import AsyncContainer, Container


def _get_plugin_providers() -> list:
    """Collect DI providers from all registered plugins.

    This queries the plugin system for providers contributed via the
    get_di_providers() hook.

    Returns:
        List of provider instances from plugins
    """
    # Import here to avoid circular dependency
    from hop3.core.plugins import get_plugin_manager  # noqa: PLC0415

    pm = get_plugin_manager()

    # Call the hook - returns list of lists
    provider_lists = pm.hook.get_di_providers()

    # Flatten into single list
    return [provider for sublist in provider_lists for provider in sublist]


def create_container() -> Container:
    """Create a new synchronous application container.

    This creates a fresh container with all providers registered,
    including providers contributed by plugins via the get_di_providers() hook.

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
    # Collect core providers
    providers = [
        ConfigProvider(),
        DatabaseProvider(),
        HopCoreProvider(),
    ]

    # Add plugin providers
    plugin_providers = _get_plugin_providers()
    providers.extend(plugin_providers)

    return make_container(*providers)


def create_async_container() -> AsyncContainer:
    """Create a new asynchronous application container.

    This creates a fresh async container with all providers registered,
    including providers contributed by plugins via the get_di_providers() hook.

    Use this for web contexts with async views (Litestar, FastAPI).

    Returns:
        AsyncContainer: Dishka async container with all providers registered

    Example:
        # For web contexts, use setup_dishka() instead (see asgi.py)
        from dishka.integrations.litestar import setup_dishka

        container = create_async_container()
        setup_dishka(container, app=app)
    """
    # Collect core providers
    providers = [
        ConfigProvider(),
        DatabaseProvider(),
        HopCoreProvider(),
    ]

    # Add plugin providers
    plugin_providers = _get_plugin_providers()
    providers.extend(plugin_providers)

    return make_async_container(*providers)
