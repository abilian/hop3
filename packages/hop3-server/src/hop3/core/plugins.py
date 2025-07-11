from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy
from pluggy import PluginManager
from snoop import snoop

from .core_plugins import CorePlugin, DockerPlugin
from .hookspecs import Hop3Spec

if TYPE_CHECKING:
    from .protocols import (
        BuildArtifact,
        BuildStrategy,
        DeploymentContext,
        DeploymentStrategy,
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
    pm.register(CorePlugin())
    pm.register(DockerPlugin())


# --- Convenience Helper Functions ---


@snoop
def get_build_strategy(context: DeploymentContext) -> BuildStrategy:
    """
    Finds and instantiates the appropriate build strategy.

    This function encapsulates the logic of checking app configuration
    and then auto-detecting a suitable strategy.
    """
    pm = get_plugin_manager()

    # The result is a list of lists, e.g., [[BuildpackBuilder], [DockerBuilder]]
    strategy_classes_list = pm.hook.register_build_strategies()

    # Flatten the list of lists into a single list of classes
    strategy_classes = [cls for sublist in strategy_classes_list for cls in sublist]

    # TODO: Add logic to check context.app_config for an explicit strategy name.
    # debug(context.app_config)
    # strategy_name_from_config = context.app_config.get_worker("build.strategy", "auto")
    strategy_name_from_config = "auto"

    if strategy_name_from_config != "auto":
        for StrategyClass in strategy_classes:
            # We assume the name is a class attribute
            if getattr(StrategyClass, "name", None) == strategy_name_from_config:
                return StrategyClass(context)
        raise RuntimeError(
            f"Configured build strategy '{strategy_name_from_config}' not found."
        )

    # Auto-detect by finding the first one that "accepts" the context.
    for StrategyClass in strategy_classes:
        instance = StrategyClass(context)
        if instance.accept():
            return instance

    raise RuntimeError("Could not find a suitable build strategy for this application.")


def get_deployment_strategy(
    context: DeploymentContext, artifact: BuildArtifact
) -> DeploymentStrategy:
    """Finds and instantiates the appropriate deployment strategy."""
    pm = get_plugin_manager()

    strategy_classes_list = pm.hook.register_deployment_strategies()
    strategy_classes = [cls for sublist in strategy_classes_list for cls in sublist]

    # TODO: Add logic to check context.app_config for an explicit strategy name.

    for StrategyClass in strategy_classes:
        instance = StrategyClass(context)
        # --- FIX HERE: The `accept` method signature takes the artifact, not context again ---
        if instance.accept(artifact):
            return instance

    raise RuntimeError(
        f"Could not find a deployment strategy compatible with artifact of kind '{artifact.kind}'."
    )


#
# def get_build_strategy(context: DeploymentContext) -> BuildStrategy:
#     """
#     Finds and instantiates the appropriate build strategy.
#
#     This function encapsulates the logic of checking app configuration
#     and then auto-detecting a suitable strategy.
#     """
#     pm = get_plugin_manager()
#
#     # Get the list of all registered BuildStrategy *classes* from all plugins.
#     # The hook returns a list of lists, so we flatten it.
#     strategy_classes = [
#         cls for sublist in pm.hook.hop3_register_build_strategies() for cls in sublist
#     ]
#
#     # TODO: Add logic to check context.app_config for an explicit strategy name.
#     # e.g., strategy_name = context.app_config.get("build.strategy", "auto")
#
#     # For now, we auto-detect by finding the first one that "accepts" the context.
#     for StrategyClass in strategy_classes:
#         # We must instantiate the class to call its `accept` method.
#         instance = StrategyClass(context)
#         if instance.accept(context):
#             return instance  # Return the instantiated strategy object
#
#     raise RuntimeError("Could not find a suitable build strategy for this application.")
#
#
# def get_deployment_strategy(
#     context: DeploymentContext, artifact: BuildArtifact
# ) -> DeploymentStrategy:
#     """Finds and instantiates the appropriate deployment strategy."""
#     pm = get_plugin_manager()
#     strategy_classes = [
#         cls
#         for sublist in pm.hook.hop3_register_deployment_strategies()
#         for cls in sublist
#     ]
#
#     for StrategyClass in strategy_classes:
#         instance = StrategyClass(context)
#         if instance.accept(artifact):
#             return instance
#
#     raise RuntimeError(
#         f"Could not find a deployment strategy compatible with artifact of kind '{artifact.kind}'."
#     )
