# Copyright (c) 2025, Abilian SAS

from __future__ import annotations

import importlib
import pkgutil
import traceback
from typing import TYPE_CHECKING

import pluggy
from devtools import debug
from pluggy import PluginManager

# Temp
from hop3.plugins.build.dummy_build.builder import DummyBuilder
from hop3.plugins.deploy.dummy_deploy.deploy import DummyDeployer

from . import hookspecs
from .hooks import hop3_hook_impl

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .protocols import (
        OS,
        Addon,
        BuildArtifact,
        Builder,
        Deployer,
        DeploymentContext,
        Proxy,
    )

# Singleton instance of the PluginManager.
_plugin_manager: pluggy.PluginManager | None = None


def get_core_plugins() -> Iterator:
    """Discover and import all core plugin modules.

    This scans the hop3.plugins package and imports all modules,
    which causes plugin instances to be created and exported.

    Returns:
        Iterator of imported plugin modules
    """
    return scan_package("hop3.plugins")


def scan_package(package_name: str) -> Iterator:
    """Import all modules in a package recursively for side effects.

    Args:
        package_name: The name of the package to scan and import modules from.

    Returns:
        Iterator that yields each module imported from the package.
    """
    for module_name in _iter_module_names(package_name):
        yield importlib.import_module(module_name)


def _iter_module_names(package_name: str) -> Iterator:
    """Generate an iterator over all module names within a given package.

    Args:
        package_name: The name of the package from which to list all modules.

    Returns:
        Iterator that yields the names of the modules within the specified package.
    """
    package_or_module = importlib.import_module(package_name)
    if not hasattr(package_or_module, "__path__"):
        # If the imported object is a module, not a package, exit the function.
        return

    path = package_or_module.__path__
    prefix = package_or_module.__name__ + "."
    for _, module_name, _ in pkgutil.walk_packages(path, prefix):
        yield module_name


def get_plugin_manager() -> PluginManager:
    """Initialize and configure a PluginManager for the 'hop3' project.

    This uses pluggy's natural discovery: plugin modules export a `plugin`
    instance which gets auto-registered when the module is imported.

    Returns:
        PluginManager: An instance of PluginManager configured with core plugins and entry points.
    """
    global _plugin_manager
    if _plugin_manager:
        return _plugin_manager

    pm = pluggy.PluginManager("hop3")

    # Import hookspecs as a module, not a class

    pm.add_hookspecs(hookspecs)

    # Register the core plugin first (provides dummy strategies)
    core_plugin = CorePlugin()
    pm.register(core_plugin)

    # Import all plugin modules and auto-discover plugin instances
    for module in get_core_plugins():
        # Each plugin module should export a `plugin` instance
        if hasattr(module, "plugin"):
            pm.register(module.plugin)

        # Also register the module itself to discover module-level hooks
        # (e.g., get_di_providers() function)
        pm.register(module)

    # For plugins that are not built-in, we load them from setuptools entry points
    pm.load_setuptools_entrypoints("hop3")

    # Cache the initialized manager in the global variable.
    _plugin_manager = pm

    return pm


class CorePlugin:
    """The plugin container for Hop3's default strategies."""

    name = "core"

    @hop3_hook_impl
    def get_builders(self) -> list:
        # This hook returns classes, not instances.
        return [DummyBuilder]

    @hop3_hook_impl
    def get_deployers(self) -> list:
        return [DummyDeployer]


#
# Convenience Helper Functions
#
def get_build_strategy(context: DeploymentContext) -> Builder:
    """
    Finds and instantiates the appropriate build strategy.

    This function encapsulates the logic of checking app configuration
    and then auto-detecting a suitable strategy.
    """
    pm = get_plugin_manager()

    # The result is a list of lists, e.g., [[BuildpackBuilder], [DockerBuilder]]
    try:
        strategy_classes_list = pm.hook.get_builders()
    except:
        traceback.print_exc()
        raise

    # Flatten the list of lists into a single list of classes
    strategy_classes: list[type[Builder]] = [
        cls for sublist in strategy_classes_list for cls in sublist
    ]
    debug(strategy_classes)

    # TODO: Add logic to check context.app_config for an explicit strategy name.
    # strategy_name_from_config = context.app_config.get_worker("build.strategy", "auto")
    strategy_name_from_config = "auto"

    # Auto-detect by finding the first one that "accepts" the context.
    if strategy_name_from_config == "auto":
        for strategy_class in strategy_classes:
            strategy = strategy_class(context)
            if strategy.accept():
                return strategy

        msg = "Could not find a suitable build strategy for this application."
        raise RuntimeError(msg)

    for strategy_class in strategy_classes:
        # We assume the name is a class attribute
        if getattr(strategy_class, "name", None) == strategy_name_from_config:
            return strategy_class(context)
    msg = f"Configured build strategy '{strategy_name_from_config}' not found."
    raise RuntimeError(msg)


def get_deployment_strategy(
    context: DeploymentContext, artifact: BuildArtifact
) -> Deployer:
    """Finds and instantiates the appropriate deployment strategy.

    This function is used during the build-deploy pipeline to auto-select
    a deployment strategy based on the artifact type.

    Args:
        context: Deployment context with app information
        artifact: Build artifact to deploy

    Returns:
        Deployer instance that accepts the artifact

    Raises:
        RuntimeError: If no compatible strategy is found
    """
    pm = get_plugin_manager()

    strategy_classes_list = pm.hook.get_deployers()
    strategy_classes = [cls for sublist in strategy_classes_list for cls in sublist]

    # TODO: Add logic to check context.app_config for an explicit strategy name.

    for strategy_class in strategy_classes:
        strategy: Deployer = strategy_class(context, artifact)
        if strategy.accept():
            return strategy

    msg = f"Could not find a deployment strategy compatible with artifact of kind '{artifact.kind}'."
    raise RuntimeError(msg)


def get_deployer_by_name(app, runtime_name: str) -> Deployer:
    """Get a deployment strategy by name for lifecycle operations.

    This function is used for lifecycle management (start, stop, restart, status)
    where we need to look up a strategy by name rather than auto-detecting.

    Args:
        app: App instance (for creating deployment context)
        runtime_name: Name of the runtime (e.g., 'uwsgi', 'docker-compose')

    Returns:
        Deployer instance for the named runtime

    Raises:
        RuntimeError: If the runtime name is not found

    Example:
        >>> strategy = get_deployer_by_name(app, 'uwsgi')
        >>> is_running = strategy.check_status()
    """
    from hop3.core.protocols import BuildArtifact, DeploymentContext  # noqa: PLC0415

    pm = get_plugin_manager()

    strategy_classes_list = pm.hook.get_deployers()
    strategy_classes: list[type[Deployer]] = [
        cls for sublist in strategy_classes_list for cls in sublist
    ]

    # Find strategy by name
    for strategy_class in strategy_classes:
        if getattr(strategy_class, "name", None) == runtime_name:
            # Create deployment context for lifecycle operations
            context = DeploymentContext(
                app_name=app.name,
                source_path=app.src_path,
                app_config={},
                app=app,
            )
            # Create dummy artifact (not needed for lifecycle ops)
            artifact = BuildArtifact(
                kind="unknown",
                location=str(app.virtualenv_path)
                if hasattr(app, "virtualenv_path")
                else "",
            )
            return strategy_class(context, artifact)

    # Provide helpful error message with available runtimes
    available_runtimes = [getattr(cls, "name", "?") for cls in strategy_classes]
    msg = (
        f"Runtime '{runtime_name}' not found. Available runtimes: {available_runtimes}"
    )
    raise RuntimeError(msg)


def get_service_strategy(service_type: str, service_name: str) -> Addon:
    """
    Finds and instantiates the appropriate service strategy.

    Args:
        service_type: The type of service (e.g., 'postgres', 'redis')
        service_name: The specific instance name for this service

    Returns:
        An instance of the requested ServiceStrategy

    Raises:
        RuntimeError: If the requested service type is not found
    """
    pm = get_plugin_manager()

    strategy_classes_list = pm.hook.get_addons()
    strategy_classes: list[type[Addon]] = [
        cls for sublist in strategy_classes_list for cls in sublist
    ]

    for strategy_class in strategy_classes:
        # Check if the strategy name matches the requested service type
        if getattr(strategy_class, "name", None) == service_type:
            return strategy_class(service_name=service_name)

    available_services = [getattr(cls, "name", "?") for cls in strategy_classes]
    msg = f"Service type '{service_type}' not found. Available services: {available_services}"
    raise RuntimeError(msg)


def get_os_strategy() -> OS:
    """
    Auto-detect and return the appropriate OS setup strategy for the current system.

    This queries all registered OS strategies via the plugin system and asks each
    one if it matches the current operating system (via the detect() method).

    Returns:
        An instance of the OS setup strategy that matches the current OS

    Raises:
        RuntimeError: If no matching OS strategy is found
    """

    pm = get_plugin_manager()

    strategy_classes_list = pm.hook.get_os_implementations()
    strategy_classes: list[type[OS]] = [
        cls for sublist in strategy_classes_list for cls in sublist
    ]

    # Try each strategy's detect() method
    for strategy_class in strategy_classes:
        strategy = strategy_class()
        if strategy.detect():
            return strategy

    available_oses = [getattr(cls, "display_name", "?") for cls in strategy_classes]
    msg = (
        f"Could not detect a supported operating system. "
        f"Available OS strategies: {available_oses}"
    )
    raise RuntimeError(msg)


def list_supported_os() -> list[str]:
    """
    Get a list of all supported operating systems.

    Returns:
        List of display names for all registered OS strategies
    """
    pm = get_plugin_manager()

    strategy_classes_list = pm.hook.get_os_implementations()
    strategy_classes = [cls for sublist in strategy_classes_list for cls in sublist]

    return [getattr(cls, "display_name", "Unknown") for cls in strategy_classes]


def get_proxy_strategy(app, env, workers: dict[str, str]) -> Proxy:
    """
    Finds and instantiates the appropriate proxy strategy based on server configuration.

    The proxy type is determined by the HOP3_PROXY_TYPE environment variable,
    which is a server-wide setting (not per-application).

    Args:
        app: The App instance to configure the proxy for
        env: The environment configuration (Env instance)
        workers: Dictionary mapping worker names to their socket paths

    Returns:
        An instance of the configured Proxy strategy

    Raises:
        RuntimeError: If the configured proxy type is not found
    """
    # Import here to avoid circular dependency
    from hop3.config import HOP3_PROXY_TYPE  # noqa: PLC0415

    pm = get_plugin_manager()

    strategy_classes_list = pm.hook.get_proxy_strategies()
    strategy_classes: list[type[Proxy]] = [
        cls for sublist in strategy_classes_list for cls in sublist
    ]

    # Get the configured proxy type (server-wide setting)
    proxy_type = HOP3_PROXY_TYPE.lower()

    # Find the matching proxy strategy
    for strategy_class in strategy_classes:
        # The proxy plugin has a name like "nginx", "caddy", "traefik"
        # We need to check the class name or look for a name attribute
        class_name = strategy_class.__name__.lower()
        if (
            proxy_type in class_name
            or getattr(strategy_class, "name", None) == proxy_type
        ):
            return strategy_class(app, env, workers)

    available_proxies = [cls.__name__ for cls in strategy_classes]
    msg = (
        f"Configured proxy type '{HOP3_PROXY_TYPE}' not found. "
        f"Available proxies: {available_proxies}. "
        f"Set HOP3_PROXY_TYPE environment variable to one of: nginx, caddy, traefik"
    )
    raise RuntimeError(msg)
