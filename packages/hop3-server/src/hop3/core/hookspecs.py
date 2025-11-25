# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dishka import Provider

from hop3.core.protocols import OS, Addon, Builder, Deployer, Proxy

from .hooks import hookspec


@hookspec
def cli_commands() -> None:
    """Get CLI commands."""


@hookspec
def get_builders() -> list[Builder]:
    """Get builders provided by this plugin.

    Returns:
        List of Builders classes
    """


@hookspec
def get_deployers() -> list[Deployer]:
    """Get deployment strategies provided by this plugin.

    Returns:
        List of Deployer classes
    """


@hookspec
def get_addons() -> list[Addon]:
    """Get addons provided by this plugin.

    Returns:
        List of Addon classes
    """


@hookspec
def get_os_implementations() -> list[OS]:
    """Get OS setup strategies provided by this plugin.

    Returns:
        List of OS classes that can detect and configure
        specific operating systems for hop3.
    """


@hookspec
def get_proxies() -> list[Proxy]:
    """Get proxy strategies provided by this plugin.

    Returns:
        List of Proxy classes that can configure reverse proxies
        (Nginx, Caddy, Traefik, etc.) for hop3 applications.
    """


@hookspec
def get_di_providers() -> list[Provider]:
    """Get DI providers from this plugin.

    Plugins can implement this hook to contribute Dishka providers
    to the application's dependency injection container.

    Returns:
        List of Dishka Provider instances that will be registered
        in the application container.

    Example:
        ```python
        from dishka import Provider, provide, Scope

        class MyPluginProvider(Provider):
            scope = Scope.APP

            @provide
            def get_my_service(self) -> MyService:
                return MyService()

        @hop3_hook_impl
        def get_di_providers() -> list:
            return [MyPluginProvider()]
        ```
    """
