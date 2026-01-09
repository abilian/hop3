# Copyright (c) 2025, Abilian SAS

from __future__ import annotations

import importlib
import pkgutil
import traceback
from typing import TYPE_CHECKING

import pluggy
from pluggy import PluginManager

from . import hookspecs

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

    # Import all plugin modules and auto-discover plugin instances
    #
    # Plugin Architecture Notes:
    # - Each plugin package can have both module-level hooks AND a plugin class
    # - Module-level hooks (e.g., get_di_providers()) are registered on the module itself
    # - Plugin class hooks (e.g., get_builders()) are registered on the plugin instance
    # - We register BOTH to support both patterns
    #
    # Example: PostgreSQL plugin has:
    #   - Module-level: @hookimpl def get_di_providers() -> list
    #   - Plugin class: PostgresqlPlugin with @hookimpl def get_addons()
    #
    # Important: To avoid duplicate registration, plugin packages should NOT
    # export the plugin instance from __init__.py if they also have a plugin.py.
    # Only plugin.py should export the plugin instance.
    for module in get_core_plugins():
        # Register the module to capture module-level hooks (like get_di_providers)
        pm.register(module)

        # Additionally register the plugin instance if it exists
        # This allows both module-level hooks and plugin-class hooks
        if hasattr(module, "plugin"):
            pm.register(module.plugin)

    # For plugins that are not built-in, we load them from setuptools entry points
    pm.load_setuptools_entrypoints("hop3")

    # Cache the initialized manager in the global variable.
    _plugin_manager = pm

    return pm


#
# Convenience Helper Functions
#
def get_builder(context: DeploymentContext) -> Builder:
    """Finds and instantiates the appropriate builder.

    This function encapsulates the logic of checking app configuration
    and then auto-detecting a suitable builder.

    Args:
        context: DeploymentContext containing app information

    Returns:
        Builder instance (LocalBuilder, DockerBuilder, etc.)

    Raises:
        RuntimeError: If no suitable builder is found
    """
    pm = get_plugin_manager()

    # The result is a list of lists, e.g., [[LocalBuilder], [DockerBuilder]]
    try:
        builder_classes_list = pm.hook.get_builders()
    except:
        traceback.print_exc()
        raise

    # Flatten the list of lists into a single list of classes
    builder_classes: list[type[Builder]] = [
        cls for sublist in builder_classes_list for cls in sublist
    ]

    # Check app_config for explicit builder selection
    # Users can set [build] builder = "docker" in hop3.toml
    build_config = context.app_config.get("build", {})
    if isinstance(build_config, dict):
        builder_name_from_config = build_config.get("builder", "auto")
    else:
        builder_name_from_config = "auto"

    # Auto-detect by finding the first one that "accepts" the context.
    if builder_name_from_config == "auto":
        rejection_reasons = []
        for builder_class in builder_classes:
            builder_name = getattr(builder_class, "name", builder_class.__name__)
            try:
                builder = builder_class(context)
                if builder.accept():
                    return builder
                # Builder didn't accept - record reason if available
                reason = getattr(builder, "rejection_reason", "no matching files")
                rejection_reasons.append(f"  - {builder_name}: {reason}")
            except Exception as e:
                rejection_reasons.append(f"  - {builder_name}: error - {e}")

        # Build helpful error message
        available_builders = [
            getattr(cls, "name", cls.__name__) for cls in builder_classes
        ]
        msg = (
            "Could not find a suitable builder for this application.\n\n"
            "This usually means the application type was not recognized.\n"
            "Make sure you have one of: Procfile, hop3.toml, requirements.txt, "
            "package.json, Cargo.toml, go.mod, or similar.\n\n"
            f"Available builders: {', '.join(available_builders)}\n\n"
            f"Source path: {context.source_path}\n\n"
            "Builder checks:\n" + "\n".join(rejection_reasons)
        )
        raise RuntimeError(msg)

    for builder_class in builder_classes:
        # We assume the name is a class attribute
        if getattr(builder_class, "name", None) == builder_name_from_config:
            return builder_class(context)
    msg = f"Configured builder '{builder_name_from_config}' not found."
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

    # No strategy accepted - build error message
    available_deployers = [
        getattr(cls, "name", cls.__name__) for cls in strategy_classes
    ]
    hints = _build_deployment_hints(artifact.kind, available_deployers)

    msg = f"Could not find a deployment strategy for artifact kind '{artifact.kind}'."
    if hints:
        msg += "\n\n" + "\n".join(hints)
    raise RuntimeError(msg)


def _build_deployment_hints(
    artifact_kind: str, available_deployers: list[str]
) -> list[str]:
    """Build helpful hints for deployment strategy errors."""
    hints: list[str] = []

    hint_builders = {
        "docker-image": _hints_for_docker_image,
        "virtualenv": _hints_for_virtualenv,
        "static": _hints_for_static,
    }

    builder = hint_builders.get(artifact_kind)
    if builder:
        hints.extend(builder(available_deployers))
    else:
        hints.extend(_hints_for_unknown_artifact(artifact_kind))

    if available_deployers:
        hints.append(f"\nAvailable deployers: {', '.join(available_deployers)}")
        hints.append("Run 'hop3 system:info -v' to see all loaded plugins.")

    return hints


def _hints_for_docker_image(available_deployers: list[str]) -> list[str]:
    """Build hints for docker-image artifact kind."""
    if not available_deployers:
        return ["No deployers are loaded. Check your hop3-server installation."]
    if "docker-compose" not in available_deployers:
        return [
            "The Docker Compose deployer is not loaded.",
            "Run 'hop3 system:info -v' to see loaded plugins.",
        ]
    return [
        "The Docker Compose deployer is available but did not accept.",
        "This may indicate an internal error. Please report this issue.",
    ]


def _hints_for_virtualenv(available_deployers: list[str]) -> list[str]:
    """Build hints for virtualenv artifact kind."""
    if "uwsgi" not in available_deployers:
        return [
            "The uWSGI deployer is not loaded.",
            "Run 'hop3 system:info -v' to see loaded plugins.",
        ]
    return [
        "The uWSGI deployer is available but did not accept.",
        "Check your app configuration:",
        "  - Ensure you have a Procfile or hop3.toml with a web worker",
        "  - Example Procfile: web: gunicorn app:app",
    ]


def _hints_for_static(available_deployers: list[str]) -> list[str]:
    """Build hints for static artifact kind."""
    if "static" not in available_deployers:
        return ["The Static deployer is not loaded."]
    return ["The Static deployer is available but did not accept."]


def _hints_for_unknown_artifact(artifact_kind: str) -> list[str]:
    """Build hints for unknown artifact kinds."""
    return [
        f"Artifact kind '{artifact_kind}' is not recognized by any deployer.",
        "Check your app configuration:",
        "  - Verify hop3.toml [build] section if present",
        "  - Ensure the build process completed successfully",
    ]


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


def get_addon(addon_type: str, addon_name: str) -> Addon:
    """Get an addon instance by type and name.

    Finds and instantiates the appropriate addon implementation.

    Args:
        addon_type: The type of addon (e.g., 'postgres', 'redis')
        addon_name: The specific instance name for this addon

    Returns:
        An instance of the requested Addon

    Raises:
        RuntimeError: If the requested addon type is not found

    Example:
        addon = get_addon('postgres', 'mydb')
        addon.create()
    """
    pm = get_plugin_manager()

    addon_classes_list = pm.hook.get_addons()
    addon_classes: list[type[Addon]] = [
        cls for sublist in addon_classes_list for cls in sublist
    ]

    for addon_class in addon_classes:
        # Check if the addon type matches
        if getattr(addon_class, "name", None) == addon_type:
            return addon_class(addon_name=addon_name)

    available_addons = [getattr(cls, "name", "?") for cls in addon_classes]
    msg = f"Addon type '{addon_type}' not found. Available addons: {available_addons}"
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

    strategy_classes_list = pm.hook.get_proxies()
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
