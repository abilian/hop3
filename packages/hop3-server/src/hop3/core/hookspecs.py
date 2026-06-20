# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

from .hooks import hookspec

if TYPE_CHECKING:
    from dishka import Provider

    from hop3.core.protocols import (
        OS,
        Addon,
        Builder,
        Deployer,
        HealthCheck,
        LanguageToolchain,
        Proxy,
        WafEngine,
    )


@hookspec
def cli_commands() -> list:  # type: ignore[empty-body]
    """Get RPC CLI command classes contributed by this plugin.

    Lets a plugin add `Command` subclasses to the server's dispatch table
    (e.g. the addon plugins contribute `addon <type> <verb>` commands such as
    `addon postgres credentials`). Collected by the RPC controller alongside
    the commands found in `hop3.commands` (see server/controllers/rpc.py).

    Returns:
        List of `hop3.commands._base.Command` subclasses.
    """


@hookspec
def get_builders() -> list[Builder]:  # type: ignore[empty-body]
    """Get builders provided by this plugin.

    Returns:
        List of Builder classes (Level 1: orchestration strategies)
    """


@hookspec
def get_language_toolchains() -> list[LanguageToolchain]:  # type: ignore[empty-body]
    """Get language-specific toolchains provided by this plugin.

    Language toolchains are used by LocalBuilder to build applications
    in specific programming languages (Python, Node, Java, etc.).

    Returns:
        List of LanguageToolchain classes for building language-specific projects.
    """


@hookspec
def get_deployers() -> list[Deployer]:  # type: ignore[empty-body]
    """Get deployment strategies provided by this plugin.

    Returns:
        List of Deployer classes
    """


@hookspec
def get_addons() -> list[Addon]:  # type: ignore[empty-body]
    """Get addons provided by this plugin.

    Returns:
        List of Addon classes
    """


@hookspec
def get_os_implementations() -> list[OS]:  # type: ignore[empty-body]
    """Get OS setup strategies provided by this plugin.

    Returns:
        List of OS classes that can detect and configure
        specific operating systems for hop3.
    """


@hookspec
def get_proxies() -> list[Proxy]:  # type: ignore[empty-body]
    """Get proxy strategies provided by this plugin.

    Returns:
        List of Proxy classes that can configure reverse proxies
        (Nginx, Caddy, Traefik, etc.) for hop3 applications.
    """


@hookspec
def get_waf_engines() -> list[WafEngine]:  # type: ignore[empty-body]
    """Get Layer-7 WAF engines provided by this plugin (ADR 048).

    Returns:
        List of WafEngine classes that compile a per-app `[waf]` policy into
        their native rules and manage the WAF service (LeWAF, later Coraza).
    """


@hookspec
def get_di_providers() -> list[Provider]:  # type: ignore[empty-body]
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


@hookspec
def get_health_checks() -> list[HealthCheck]:  # type: ignore[empty-body]
    """Get health checks provided by this plugin.

    Health checks verify that services (databases, caches, etc.) are
    properly configured and accessible. They are run:
    - During server startup (warnings logged for failures)
    - Via the `system check` command

    Returns:
        List of HealthCheck instances that can verify service health.

    Example:
        ```python
        from hop3.core.protocols import HealthCheck, HealthCheckResult

        class MySQLHealthCheck:
            name = "mysql"

            def is_configured(self) -> bool:
                admin = MySQLAdmin.from_config()
                return admin.superuser_password is not None

            def check(self) -> HealthCheckResult:
                # ... perform check ...
                return HealthCheckResult(name="MySQL", passed=True, message="OK")

        @hookimpl
        def get_health_checks() -> list:
            return [MySQLHealthCheck()]
        ```
    """
