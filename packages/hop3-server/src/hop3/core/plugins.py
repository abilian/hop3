# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

import pluggy
from devtools import debug
from pluggy import PluginManager

# Temp
from hop3.plugins.build.dummy_build.builder import DummyBuildStrategy
from hop3.plugins.deploy.dummy_deploy.deploy import DummyDeployer

from .hooks import hop3_hook_impl
from .hookspecs import Hop3Spec

if TYPE_CHECKING:
    from .protocols import (
        BuildArtifact,
        BuildStrategy,
        DeploymentContext,
        DeploymentStrategy,
        ServiceStrategy,
    )

# Singleton instance of the PluginManager.
_plugin_manager: pluggy.PluginManager | None = None


def get_plugin_manager() -> pluggy.PluginManager:
    """
    Initializes and returns the singleton Hop3 PluginManager.

    This function is the main entry point for accessing the plugin system.
    It creates the manager on its first call and then returns the cached
    instance on subsequent calls. It discovers all built-in and external plugins.

    Returns:
        The configured pluggy.PluginManager instance.
    """
    global _plugin_manager
    if _plugin_manager:
        return _plugin_manager

    pm = pluggy.PluginManager("hop3")
    pm.add_hookspecs(Hop3Spec)

    # 3. Load all external plugins.
    # This looks for installed packages that have a `[hop3.plugins]`
    # section in their `pyproject.toml` or `entry_points` in `setup.py`.
    pm.load_setuptools_entrypoints("hop3")

    # 4. Manually register the core, built-in plugins.
    register_core_plugins(pm)

    # Cache the initialized manager in the global variable.
    _plugin_manager = pm

    return pm


def register_core_plugins(pm: PluginManager) -> None:
    """
    Registers the core Hop3 plugins with the PluginManager.

    This function is called at startup to ensure that the built-in strategies
    (like Buildpack and uWSGI) are always available.
    """
    # Register the PostgreSQL service plugin
    from hop3.plugins.services.postgresql.plugin import PostgresqlPlugin

    pm.register(PostgresqlPlugin())

    # Register the native build plugin
    from hop3.plugins.build.native_build.plugin import NativeBuildPlugin

    pm.register(NativeBuildPlugin())

    # TODO: really register the core plugins.
    # Or do we?
    # pm.register(CorePlugin())
    # pm.register(DockerPlugin())
    # pm.register(SmoPlugin())


class CorePlugin:
    """The plugin container for Hop3's default strategies."""

    name = "core"

    @hop3_hook_impl
    def get_build_strategies(self) -> list[type[BuildStrategy]]:
        # This hook returns classes, not instances.
        return [DummyBuildStrategy]

    @hop3_hook_impl
    def get_deployment_strategies(self) -> list[type[DeploymentStrategy]]:
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

    msg = f"Service type '{service_type}' not found. Available services: {[getattr(cls, 'name', '?') for cls in strategy_classes]}"
    raise RuntimeError(msg)
