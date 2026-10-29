# Copyright (c) 2025, Abilian SAS

# ruff:file-ignore[global-statement]
# `_plugin_manager` is bootstrap state for the Dishka container itself
# (di/container.py calls get_plugin_manager() to *discover* providers, so
# the PluginManager has to exist before the container can be built).
# Lazy-init singleton is the right shape; can't be a Dishka provider.

from __future__ import annotations

import inspect
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, TypeVar

import pluggy
from pluggy import PluginManager

from hop3.lib.console import Abort
from hop3.lib.decision_log import get_decision_logger
from hop3.lib.diagnostics import Diagnosis, abort_with_diagnosis, format_diagnosis
from hop3.lib.scanner import scan_package

from . import hookspecs
from .artifacts import ARTIFACT_FILENAME
from .protocols import (
    BuildArtifact,
    DeploymentContext,
)

if TYPE_CHECKING:
    from types import ModuleType

    from hop3.core.env import Env
    from hop3.orm import App

    from .protocols import (
        OS,
        Addon,
        Builder,
        Deployer,
        Proxy,
        WafEngine,
    )

T = TypeVar("T")


class NeverBuiltError(RuntimeError):
    """A lifecycle operation on an app that has no build artifact."""


# Singleton instance of the PluginManager.
_plugin_manager: pluggy.PluginManager | None = None


#: The entry-point group external plugins declare (`[project.entry-points."hop3"]`).
ENTRY_POINT_GROUP = "hop3"

#: Groups a distribution may declare by mistake; pluggy would ignore them.
MISSPELLED_ENTRY_POINT_GROUPS = ("hop3.plugins", "hop3_plugins")


def get_core_plugins() -> list[ModuleType]:
    """Import every module under ``hop3.plugins`` and return them."""
    return scan_package("hop3.plugins")


def get_plugin_manager() -> PluginManager:
    """
    Initialize and configure a PluginManager for the 'hop3' project.

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
        if plugin is None or inspect.ismodule(plugin):
            continue
        # A package whose ``__init__`` re-exports its ``plugin.py``'s instance
        # shows the same object twice; it is one plugin, registered once. A
        # *different* object under a taken name still raises below.
        if pm.is_registered(plugin):
            continue
        # Register under the plugin's own `name`. Without it pluggy keys the
        # plugin by str(id(obj)), so get_plugin("nginx") / set_blocked() /
        # entry-point dedup can never find it despite every plugin
        # declaring a name. A duplicate name now raises at startup, which
        # is the correct answer to two plugins claiming one identity.
        pm.register(plugin, name=getattr(plugin, "name", None) or None)

    # For plugins that are not built-in, we load them from setuptools entry points
    _refuse_misnamed_entry_points()
    pm.load_setuptools_entrypoints(ENTRY_POINT_GROUP)

    # A hookimpl whose spec doesn't exist (a typo, or a hook that was renamed
    # without updating its implementers) is otherwise a permanent silent no-op.
    pm.check_pending()

    # Cache the initialized manager in the global variable.
    _plugin_manager = pm

    return pm


def _refuse_misnamed_entry_points() -> None:
    """Abort when an installed distribution declares a plugin under a wrong group."""
    misnamed = [
        f"{ep.dist.name if ep.dist else '?'} ({ep.group}: {ep.name} = {ep.value})"
        for group in MISSPELLED_ENTRY_POINT_GROUPS
        for ep in entry_points(group=group)
    ]
    if misnamed:
        abort_with_diagnosis(
            Diagnosis(
                component="Plugin manager",
                action="load external plugins",
                reason=(
                    "these distributions declare a Hop3 plugin under an entry-point "
                    f"group Hop3 does not read: {', '.join(misnamed)}"
                ),
                hint=(
                    f'declare it under [project.entry-points."{ENTRY_POINT_GROUP}"] '
                    "in the plugin's pyproject.toml and reinstall it"
                ),
            )
        )


#
# Convenience Helper Functions
#
def _plugin_name(cls: type) -> str:
    return getattr(cls, "name", None) or cls.__name__


def _select_named(
    classes: list[type[T]], name: str, *, what: str, hint: str
) -> type[T]:
    """The one class called ``name``, else abort naming the ones loaded."""
    matches = [cls for cls in classes if getattr(cls, "name", None) == name]
    if len(matches) != 1:
        available = ", ".join(_plugin_name(cls) for cls in classes) or "none"
        abort_with_diagnosis(
            Diagnosis(
                component="Plugin manager",
                action=f"select the {what} '{name}'",
                reason=(
                    f"no {what} named '{name}' is loaded (loaded: {available})"
                    if not matches
                    else f"{len(matches)} loaded {what}s are named '{name}'"
                ),
                hint=hint if not matches else "uninstall the duplicate plugin",
                troubleshooting=[
                    "Run 'hop3 system info -v' to see all loaded plugins."
                ],
            )
        )
    return matches[0]


def _configured_name(context: DeploymentContext, section: str, key: str) -> str:
    """``[section].key`` from the app's hop3.toml, or ``"auto"``."""
    # Typed `object`: this is unvalidated app_config data, so a malformed
    # section must stay visible to the isinstance guards below.
    hop3_config = context.app_config.get("hop3_config", {})
    config: object = (
        hop3_config.get(section, {}) if isinstance(hop3_config, dict) else {}
    )
    name = config.get(key, "auto") if isinstance(config, dict) else "auto"
    return name or "auto"


def get_builder(context: DeploymentContext) -> Builder:
    """
    Finds and instantiates the appropriate builder.

    ``[build].builder`` in hop3.toml names it; otherwise every builder is
    asked whether it builds the app. A builder declaring ``fallback = True``
    (the local builder: it accepts any source a toolchain recognises) is
    chosen only when no other builder accepts, since a Dockerfile or a
    hop3.nix is a deliberate choice of build. Two non-fallback builders
    accepting is a contradiction the user must resolve.

    Raises:
        Abort: no builder, or several, accept the app; a builder failed.
    """
    pm = get_plugin_manager()
    builder_classes: list[type[Builder]] = [
        cls for sublist in pm.hook.get_builders() for cls in sublist
    ]
    available = [_plugin_name(cls) for cls in builder_classes]
    decision_logger = get_decision_logger()

    configured = _configured_name(context, "build", "builder")
    if configured != "auto":
        builder_class = _select_named(
            builder_classes,
            configured,
            what="builder",
            hint=f"set [build].builder to one of: {', '.join(available)}",
        )
        decision_logger.log_builder_decision(
            configured, "explicitly set in hop3.toml [build].builder", explicit=True
        )
        return builder_class(context)

    accepted: list[Builder] = []
    rejections: list[str] = []
    for builder_class in builder_classes:
        name = _plugin_name(builder_class)
        try:
            builder = builder_class(context)
            accepts = builder.accept()
        except Abort:
            # A deliberate refusal of a misconfigured app (e.g. NixBuilder
            # rejecting both hop3.nix and [nix].template): an answer.
            raise
        except Exception as e:
            # A probe that crashed has not said no: moving on to the next
            # builder would build the app some other way without a word.
            raise Abort(
                format_diagnosis(
                    Diagnosis(
                        component="Builder selection",
                        action=f"ask the '{name}' builder whether it builds "
                        f"'{context.app_name}'",
                        reason=f"{type(e).__name__}: {e}",
                        hint=(
                            f"this is a bug in the '{name}' builder plugin: report "
                            "it, or set [build].builder to another builder"
                        ),
                    )
                )
            ) from e
        if accepts:
            accepted.append(builder)
        else:
            reason = getattr(builder, "rejection_reason", "declined")
            rejections.append(f"{name}: {reason}")

    specific = [b for b in accepted if not b.fallback]
    candidates = specific or accepted
    if not candidates:
        abort_with_diagnosis(
            Diagnosis(
                component="Builder selection",
                action=f"build '{context.app_name}'",
                reason=f"no builder recognises the source at {context.source_path}",
                hint=(
                    "add what one of these builders looks for, or set "
                    f"[build].builder to one of: {', '.join(available)}"
                ),
                troubleshooting=rejections,
            )
        )
    if len(candidates) > 1:
        names = [_plugin_name(type(b)) for b in candidates]
        reasons = [
            f"{_plugin_name(type(b))}: "
            f"{getattr(b, 'acceptance_reason', 'accepts the app')}"
            for b in candidates
        ]
        abort_with_diagnosis(
            Diagnosis(
                component="Builder selection",
                action=f"build '{context.app_name}'",
                reason=f"several builders accept the app: {', '.join(names)}",
                hint=f"set [build].builder in hop3.toml to one of: {', '.join(names)}",
                troubleshooting=reasons,
            )
        )
    builder = candidates[0]
    reason = getattr(builder, "acceptance_reason", "matched project files")
    decision_logger.log_builder_decision(
        _plugin_name(type(builder)),
        f"auto-detected ({reason})",
        explicit=False,
        alternatives=available,
    )
    return builder


def get_deployer(context: DeploymentContext, artifact: BuildArtifact) -> Deployer:
    """
    Find and instantiate the deployer for an artifact.

    ``[deploy].deployer`` in hop3.toml names it, mirroring ``[build].builder``;
    otherwise the one deployer accepting the artifact is chosen. Deployers
    accept disjoint artifact kinds, so two accepting is a conflict between
    plugins, never an order to resolve silently.

    Raises:
        Abort: no deployer, or several, accept the artifact.
    """
    pm = get_plugin_manager()
    deployer_classes: list[type[Deployer]] = [
        cls for sublist in pm.hook.get_deployers() for cls in sublist
    ]
    available = [_plugin_name(cls) for cls in deployer_classes]
    decision_logger = get_decision_logger()

    configured = _configured_name(context, "deploy", "deployer")
    if configured != "auto":
        deployer_class = _select_named(
            deployer_classes,
            configured,
            what="deployer",
            hint=f"set [deploy].deployer to one of: {', '.join(available)}",
        )
        decision_logger.log_deployer_decision(
            configured,
            "explicitly set in hop3.toml [deploy].deployer",
            artifact_kind=artifact.kind,
        )
        return deployer_class(context, artifact)

    candidates = [
        deployer
        for deployer in (cls(context, artifact) for cls in deployer_classes)
        if deployer.accept()
    ]
    if len(candidates) != 1:
        names = [_plugin_name(type(d)) for d in candidates]
        abort_with_diagnosis(
            Diagnosis(
                component="Deployer selection",
                action=f"deploy '{context.app_name}'",
                reason=(
                    f"no loaded deployer accepts a '{artifact.kind}' artifact "
                    f"(loaded: {', '.join(available) or 'none'})"
                    if not candidates
                    else f"several deployers accept a '{artifact.kind}' "
                    f"artifact: {', '.join(names)}"
                ),
                hint=(
                    "check that the builder produced the artifact you expect, "
                    "or install the plugin that deploys it"
                    if not candidates
                    else f"set [deploy].deployer in hop3.toml to one of: "
                    f"{', '.join(names)}"
                ),
                troubleshooting=[
                    "Run 'hop3 system info -v' to see all loaded plugins."
                ],
            )
        )
    deployer = candidates[0]
    decision_logger.log_deployer_decision(
        deployer.name,
        f"matched artifact kind '{artifact.kind}'",
        artifact_kind=artifact.kind,
    )
    return deployer


def get_probe_deployer(app: App, runtime_name: str) -> Deployer:
    """
    The deployer named ``runtime_name``, to probe whether the app is running.

    It gets the last deploy's saved artifact and no app config:
    ``check_status`` reads process state only. Parsing hop3.toml here made a
    syntax error in a running app's hop3.toml break ``hop3 app status`` and
    the state sync, and re-parsed every app's config on each sync cycle.

    Raises:
        RuntimeError: no deployer has that name, or the app's build artifact
            is unreadable.
        NeverBuiltError: the app has no build artifact.
    """
    pm = get_plugin_manager()
    deployer_classes: list[type[Deployer]] = [
        cls for sublist in pm.hook.get_deployers() for cls in sublist
    ]
    deployer_class = next(
        (cls for cls in deployer_classes if _plugin_name(cls) == runtime_name), None
    )
    if deployer_class is None:
        available = [_plugin_name(cls) for cls in deployer_classes]
        msg = f"Deployer '{runtime_name}' not found. Available: {available}"
        raise RuntimeError(msg)

    artifact_path = app.app_path / ARTIFACT_FILENAME
    artifact = BuildArtifact.load(artifact_path)
    if artifact is None:
        msg = f"App '{app.name}' was never built: {artifact_path} does not exist."
        raise NeverBuiltError(msg)
    context = DeploymentContext(
        app_name=app.name,
        source_path=app.src_path,
        app_config={},
        app=app,
    )
    return deployer_class(context, artifact)


class UnknownAddonTypeError(RuntimeError):
    """No loaded addon plugin has the requested type name."""


def get_addon(addon_type: str, addon_name: str) -> Addon:
    """
    Get an addon instance by type and name.

    Finds and instantiates the appropriate addon implementation.

    Args:
        addon_type: The type of addon (e.g., 'postgres', 'redis')
        addon_name: The specific instance name for this addon

    Returns:
        An instance of the requested Addon

    Raises:
        UnknownAddonTypeError: If the requested addon type is not found

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
    raise UnknownAddonTypeError(msg)


def get_waf_engine(name: str = "lewaf") -> WafEngine:
    """
    Return the Layer-7 WAF engine named ``name`` (ADR 050; default LeWAF).

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
    The OS setup strategy for the current system.

    Every registered strategy's ``detect()`` is asked; exactly one must claim
    the host. Two claiming it is a plugin conflict, not an order to resolve.

    Raises:
        Abort: no strategy, or several, detect the current OS.
    """
    pm = get_plugin_manager()
    strategy_classes: list[type[OS]] = [
        cls for sublist in pm.hook.get_os_implementations() for cls in sublist
    ]
    detected = [s for s in (cls() for cls in strategy_classes) if s.detect()]
    if len(detected) != 1:
        available = [getattr(cls, "display_name", "?") for cls in strategy_classes]
        abort_with_diagnosis(
            Diagnosis(
                component="OS setup",
                action="detect the operating system",
                reason=(
                    f"no OS strategy recognises this host (supported: {available})"
                    if not detected
                    else "several OS strategies claim this host: "
                    + ", ".join(_plugin_name(type(s)) for s in detected)
                ),
                hint=(
                    "run Hop3 on a supported distribution"
                    if not detected
                    else "uninstall the OS plugin that should not match this host"
                ),
                troubleshooting=["cat /etc/os-release"],
            )
        )
    return detected[0]


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


def get_proxy_strategy(app: App, env: Env, workers: dict[str, str]) -> Proxy:
    """
    Instantiate the server's proxy strategy for one app.

    Args:
        app: The App instance to configure the proxy for
        env: The environment configuration (Env instance)
        workers: Dictionary mapping worker names to their socket paths

    Raises:
        Abort: no proxy, or several, carry the configured name.
    """
    return get_proxy_class()(app, env, workers)


def get_proxy_class() -> type[Proxy]:
    """
    The proxy strategy class the server is configured with.

    The proxy type is determined by the HOP3_PROXY_TYPE environment variable,
    which is a server-wide setting (not per-application). A deploy asks the
    class what it can do before it builds anything.

    Raises:
        Abort: no proxy, or several, carry the configured name.
    """
    # Import here to avoid circular dependency
    from hop3.config import HOP3_PROXY_TYPE  # ruff:ignore[import-outside-top-level]

    pm = get_plugin_manager()
    strategy_classes: list[type[Proxy]] = [
        cls for sublist in pm.hook.get_proxies() for cls in sublist
    ]
    names = ", ".join(_plugin_name(cls) for cls in strategy_classes)
    return _select_named(
        strategy_classes,
        HOP3_PROXY_TYPE.lower(),
        what="proxy",
        hint=f"set HOP3_PROXY_TYPE in the server configuration to one of: {names}",
    )
