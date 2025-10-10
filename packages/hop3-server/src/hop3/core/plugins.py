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
from hop3.plugins.build.dummy_build.builder import DummyBuildStrategy
from hop3.plugins.deploy.dummy_deploy.deploy import DummyDeployer

from .hooks import hop3_hook_impl

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .protocols import (
        BuildArtifact,
        BuildStrategy,
        DeploymentContext,
        DeploymentStrategy,
        OSSetupStrategy,
        ServiceStrategy,
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
    from . import hookspecs

    pm.add_hookspecs(hookspecs)

    # Register the core plugin first (provides dummy strategies)
    core_plugin = CorePlugin()
    pm.register(core_plugin)

    # Import all plugin modules and auto-discover plugin instances
    for module in get_core_plugins():
        # Each plugin module should export a `plugin` instance
        if hasattr(module, "plugin"):
            pm.register(module.plugin)

    # For plugins that are not built-in, we load them from setuptools entry points
    pm.load_setuptools_entrypoints("hop3")

    # Cache the initialized manager in the global variable.
    _plugin_manager = pm

    return pm


class CorePlugin:
    """The plugin container for Hop3's default strategies."""

    name = "core"

    @hop3_hook_impl
    def get_build_strategies(self) -> list:
        # This hook returns classes, not instances.
        return [DummyBuildStrategy]

    @hop3_hook_impl
    def get_deployment_strategies(self) -> list:
        return [DummyDeployer]


#
# Convenience Helper Functions
#
def get_build_strategy(context: DeploymentContext) -> BuildStrategy:
    """
    Finds and instantiates the appropriate build strategy.

    This function encapsulates the logic of checking app configuration
    and then auto-detecting a suitable strategy.
    """
    pm = get_plugin_manager()

    # The result is a list of lists, e.g., [[BuildpackBuilder], [DockerBuilder]]
    try:
        strategy_classes_list = pm.hook.get_build_strategies()
    except:
        traceback.print_exc()
        raise

    # Flatten the list of lists into a single list of classes
    strategy_classes: list[type[BuildStrategy]] = [
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
) -> DeploymentStrategy:
    """Finds and instantiates the appropriate deployment strategy."""
    pm = get_plugin_manager()

    strategy_classes_list = pm.hook.get_deployment_strategies()
    strategy_classes = [cls for sublist in strategy_classes_list for cls in sublist]

    # TODO: Add logic to check context.app_config for an explicit strategy name.

    for strategy_class in strategy_classes:
        strategy: DeploymentStrategy = strategy_class(context, artifact)
        if strategy.accept():
            return strategy

    msg = f"Could not find a deployment strategy compatible with artifact of kind '{artifact.kind}'."
    raise RuntimeError(msg)


def get_service_strategy(service_type: str, service_name: str) -> ServiceStrategy:
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

    strategy_classes_list = pm.hook.get_service_strategies()
    strategy_classes: list[type[ServiceStrategy]] = [
        cls for sublist in strategy_classes_list for cls in sublist
    ]

    for strategy_class in strategy_classes:
        # Check if the strategy name matches the requested service type
        if getattr(strategy_class, "name", None) == service_type:
            return strategy_class(service_name)

    available_services = [getattr(cls, "name", "?") for cls in strategy_classes]
    msg = f"Service type '{service_type}' not found. Available services: {available_services}"
    raise RuntimeError(msg)


def get_os_strategy() -> OSSetupStrategy:
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

    strategy_classes_list = pm.hook.get_os_strategies()
    strategy_classes: list[type[OSSetupStrategy]] = [
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

    strategy_classes_list = pm.hook.get_os_strategies()
    strategy_classes = [cls for sublist in strategy_classes_list for cls in sublist]

    return [getattr(cls, "display_name", "Unknown") for cls in strategy_classes]
