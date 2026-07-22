# Copyright (c) 2025, Abilian SAS

# ruff:file-ignore[global-statement]
# `_plugin_manager` is bootstrap state for the Dishka container itself
# (di/container.py calls get_plugin_manager() to *discover* providers, so
# the PluginManager has to exist before the container can be built).
# Lazy-init singleton is the right shape; can't be a Dishka provider.

from __future__ import annotations

import importlib
import inspect
import pkgutil
import traceback
from typing import TYPE_CHECKING

import pluggy
from pluggy import PluginManager

from hop3.lib.decision_log import get_decision_logger

from . import hookspecs
from .protocols import (
    BuildArtifact,
    DeploymentContext,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .protocols import (
        OS,
        Addon,
        Builder,
        Deployer,
        Proxy,
        WafEngine,
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
    # Important: register a module's ``plugin`` only when it's a plugin
    # *instance*, never a module. Importing a ``plugin.py`` submodule binds it
    # as a ``plugin`` attribute on its parent package (Python's normal import
    # behaviour), so a package ``__init__`` whose ``plugin.py`` was already
    # imported would otherwise re-register that submodule under the same name as
    # the later ``plugin.py`` pass — a duplicate-registration crash that only
    # surfaces when the submodule is imported before this build runs.
    for module in get_core_plugins():
        # Register the module to capture module-level hooks (like get_di_providers)
        pm.register(module)

        # Additionally register the plugin instance if it exists
        # This allows both module-level hooks and plugin-class hooks
        plugin = getattr(module, "plugin", None)
        if plugin is not None and not inspect.ismodule(plugin):
            pm.register(plugin)

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
    # The hop3.toml config is nested under "hop3_config" key
    hop3_config = context.app_config.get("hop3_config", {})
    build_config = hop3_config.get("build", {}) if isinstance(hop3_config, dict) else {}
    if isinstance(build_config, dict):
        builder_name_from_config = build_config.get("builder", "auto")
    else:
        builder_name_from_config = "auto"

    decision_logger = get_decision_logger()

    # Auto-detect by finding the first one that "accepts" the context.
    if builder_name_from_config == "auto":
        rejection_reasons = []
        available_builders = [
            getattr(cls, "name", cls.__name__) for cls in builder_classes
        ]
        for builder_class in builder_classes:
            builder_name = getattr(builder_class, "name", builder_class.__name__)
            try:
                builder = builder_class(context)
                if builder.accept():
                    # Log the auto-detection decision
                    reason = getattr(
                        builder, "acceptance_reason", "matched project files"
                    )
                    decision_logger.log_builder_decision(
                        builder_name,
                        f"auto-detected ({reason})",
                        explicit=False,
                        alternatives=available_builders,
                    )
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
            # Log the explicit selection
            decision_logger.log_builder_decision(
                builder_name_from_config,
                "explicitly set in hop3.toml [build].builder",
                explicit=True,
            )
            return builder_class(context)
    msg = f"Configured builder '{builder_name_from_config}' not found."
    raise RuntimeError(msg)


def get_deployer(context: DeploymentContext, artifact: BuildArtifact) -> Deployer:
    """Find and instantiate the appropriate deployer for an artifact.

    This function is used during the build-deploy pipeline to auto-select
    a deployer based on the artifact type.

    Args:
        context: Deployment context with app information
        artifact: Build artifact to deploy

    Returns:
        Deployer instance that accepts the artifact

    Raises:
        RuntimeError: If no compatible deployer is found
    """
    pm = get_plugin_manager()

    deployer_classes: list[type[Deployer]] = [
        cls for sublist in pm.hook.get_deployers() for cls in sublist
    ]

    # Import decision logger
    from hop3.lib.decision_log import (
        get_decision_logger,
    )

    decision_logger = get_decision_logger()

    # TODO: Add logic to check context.app_config for an explicit deployer name.

    for deployer_class in deployer_classes:
        deployer: Deployer = deployer_class(context, artifact)
        if deployer.accept():
            decision_logger.log_deployer_decision(
                deployer_class.name,  # Required by Deployer protocol
                f"matched artifact kind '{artifact.kind}'",
                artifact_kind=artifact.kind,
            )
            return deployer

    # No deployer accepted - build error message
    available = [cls.name for cls in deployer_classes]
    hints = _build_deployment_hints(artifact.kind, available)

    msg = f"No deployer found for artifact kind '{artifact.kind}'."
    if hints:
        msg += "\n\n" + "\n".join(hints)
    raise RuntimeError(msg)


def _build_deployment_hints(
    artifact_kind: str, available_deployers: list[str]
) -> list[str]:
    """Build helpful hints when no deployer accepts an artifact."""
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
        hints.append("Run 'hop3 system info -v' to see all loaded plugins.")

    return hints


def _hints_for_docker_image(available_deployers: list[str]) -> list[str]:
    """Build hints for docker-image artifact kind."""
    if not available_deployers:
        return ["No deployers are loaded. Check your hop3-server installation."]
    if "docker-compose" not in available_deployers:
        return [
            "The Docker Compose deployer is not loaded.",
            "Run 'hop3 system info -v' to see loaded plugins.",
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
            "Run 'hop3 system info -v' to see loaded plugins.",
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
    """Get a deployer by name for lifecycle operations.

    This function is used for lifecycle management (start, stop, restart, status)
    where we need to look up a deployer by name rather than auto-detecting.

    Args:
        app: App instance (for creating deployment context)
        runtime_name: Name of the deployer (e.g., 'uwsgi', 'docker-compose')

    Returns:
        Deployer instance for the named runtime

    Raises:
        RuntimeError: If the deployer name is not found

    Example:
        >>> deployer = get_deployer_by_name(app, 'uwsgi')
        >>> is_running = deployer.check_status()
    """
    pm = get_plugin_manager()

    deployer_classes: list[type[Deployer]] = [
        cls for sublist in pm.hook.get_deployers() for cls in sublist
    ]

    # Find deployer by name
    for deployer_class in deployer_classes:
        if deployer_class.name == runtime_name:
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
            return deployer_class(context, artifact)

    # Provide helpful error message with available deployers
    available = [cls.name for cls in deployer_classes]
    msg = f"Deployer '{runtime_name}' not found. Available: {available}"
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


def get_waf_engine(name: str = "lewaf") -> WafEngine:
    """Return the Layer-7 WAF engine named ``name`` (ADR 050; default LeWAF).

    Args:
        name: the engine name (``[waf].engine``); defaults to ``lewaf``.

    Returns:
        An instance of the matching ``WafEngine``.

    Raises:
        RuntimeError: if no engine with that name is registered.
    """
    pm = get_plugin_manager()
    engine_classes: list[type[WafEngine]] = [
        cls for sublist in pm.hook.get_waf_engines() for cls in sublist
    ]
    for engine_class in engine_classes:
        if getattr(engine_class, "name", None) == name:
            return engine_class()
    available = [getattr(c, "name", "?") for c in engine_classes]
    msg = f"WAF engine '{name}' not found. Available engines: {available}"
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
    from hop3.config import HOP3_PROXY_TYPE  # ruff:ignore[import-outside-top-level]

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
