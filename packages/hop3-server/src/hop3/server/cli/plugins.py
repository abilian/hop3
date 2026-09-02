# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import types
from typing import TYPE_CHECKING, ClassVar, Protocol

from hop3.config import HOP3_PROXY_TYPE
from hop3.core.plugins import get_plugin_manager
from hop3.lib.console import bold, dim, echo, green
from hop3.lib.registry import register
from hop3.server.asgi import create_app

from . import Command

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from pluggy import PluginManager


class _Named(Protocol):
    """Protocol for objects with a name attribute."""

    name: str


# Strategy hooks that provide lists of strategies
STRATEGY_HOOKS = {
    "get_builders",
    "get_deployers",
    "get_addons",
    "get_language_toolchains",
    "get_proxies",
    "get_os_implementations",
}


@register
class Plugins(Command):
    """Lists all plugins."""

    name = "plugins"

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add command-specific arguments."""
        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            dest="verbose_plugins",
            help="Show detailed information about each plugin",
        )

    def run(self, *, verbose_plugins: bool = False) -> None:
        # create_app() has the side effect of importing every command and
        # plugin module, which is what registers them with the plugin
        # manager. Discarding the return value is intentional: we only need
        # the registration side effect, not the ASGI app.
        create_app()
        pm = get_plugin_manager()

        if verbose_plugins:
            self._print_verbose(pm)
        else:
            self._print_summary(pm)

    def _print_summary(self, pm: PluginManager) -> None:
        """Print a compact, flat summary of capabilities."""
        capabilities = self._gather_capabilities(pm)

        title = "Hop3 Capabilities"
        print(bold(title))
        print("=" * len(title))
        print()

        # Flat list - one line per capability type
        if capabilities["builders"]:
            builders = ", ".join(sorted(capabilities["builders"]))
            print(f"{bold('Builders:')}    {builders}")

        if capabilities["toolchains"]:
            langs = ", ".join(sorted(capabilities["toolchains"]))
            print(f"{bold('Languages:')}   {langs}")

        if capabilities["deployers"]:
            deployers = ", ".join(sorted(capabilities["deployers"]))
            print(f"{bold('Deployers:')}   {deployers}")

        if capabilities["proxies"]:
            active_proxy = self._get_active_proxy()
            proxies_display = []
            for p in sorted(capabilities["proxies"]):
                if p == active_proxy:
                    proxies_display.append(f"{p} {green('✓')}")
                else:
                    proxies_display.append(p)
            print(f"{bold('Proxies:')}     {', '.join(proxies_display)}")

        if capabilities["os_support"]:
            detected_os = self._get_detected_os(pm)
            os_display = []
            for os_name in sorted(capabilities["os_support"]):
                if os_name == detected_os:
                    os_display.append(f"{os_name} {green('✓')}")
                else:
                    os_display.append(os_name)
            print(f"{bold('OS Support:')}  {', '.join(os_display)}")

        if capabilities["addons"]:
            addons = ", ".join(sorted(capabilities["addons"]))
            print(f"{bold('Addons:')}      {addons}")

        print()
        print(dim(f"{green('✓')} = active/detected on this system"))
        print(dim("Use --verbose for detailed plugin information."))

    # (capability key, hook name, how to name one contributed object).
    # Six methods used to do this, differing only in these three values and
    # each ending in `except Exception: pass` — so a plugin that raised while
    # being listed vanished from `hop3 plugins` output with no indication that
    # anything was missing.
    _CAPABILITY_SOURCES: ClassVar[tuple[tuple[str, str, str], ...]] = (
        ("builders", "get_builders", "name"),
        ("deployers", "get_deployers", "name"),
        ("toolchains", "get_language_toolchains", "language"),
        ("proxies", "get_proxies", "proxy"),
        ("os_support", "get_os_implementations", "lower"),
        ("addons", "get_addons", "lower"),
    )

    def _gather_capabilities(self, pm: PluginManager) -> dict[str, set[str]]:
        """
        Gather all capabilities from registered plugins.

        A hook that raises is reported, not hidden: this output is what an
        operator reads to find out what the server can do, so quietly dropping
        a broken plugin turns a plugin bug into "that feature doesn't exist".
        """
        capabilities: dict[str, set[str]] = {
            key: set() for key, _, _ in self._CAPABILITY_SOURCES
        }

        for key, hook_name, naming in self._CAPABILITY_SOURCES:
            try:
                contributed = getattr(pm.hook, hook_name)()
            except Exception as e:
                echo(
                    f"Warning: plugin hook {hook_name}() failed, so the "
                    f"{key} list below is incomplete: {type(e).__name__}: {e}",
                    fg="red",
                )
                continue
            for group in contributed:
                for obj in group:
                    if name := self._capability_name(obj, naming):
                        capabilities[key].add(name)

        return capabilities

    def _capability_name(self, obj: object, naming: str) -> str | None:
        """Display name for one contributed plugin object, or None to skip."""
        if naming == "proxy":
            return self._extract_proxy_name(obj)

        raw: str = str(getattr(obj, "name", "") or getattr(obj, "__name__", ""))
        if not raw:
            return None
        if naming == "language":
            return self._toolchain_to_language(raw)
        if naming == "lower":
            return raw.lower()
        return None if raw == "dummy" else raw

    def _toolchain_to_language(self, toolchain_name: str) -> str | None:
        """
        Convert toolchain name to user-friendly language name.

        Returns None for non-language toolchains (like static).
        """
        mapping = {
            "python": "Python",
            "node": "Node.js",
            "nodejs": "Node.js",
            "ruby": "Ruby",
            "go": "Go",
            "golang": "Go",
            "rust": "Rust",
            "clojure": "Clojure",
            "java": "Java",
            "php": "PHP",
        }
        return mapping.get(toolchain_name.lower())

    def _extract_proxy_name(self, proxy_class: object) -> str:
        """Extract clean proxy name from class."""
        # First try explicit name attribute
        if hasattr(proxy_class, "name"):
            return proxy_class.name

        # Extract from class name (e.g., NginxVirtualHost -> nginx)
        class_name = getattr(proxy_class, "__name__", type(proxy_class).__name__)
        # Remove common suffixes
        for suffix in ["VirtualHost", "Proxy", "Strategy"]:
            class_name = class_name.removesuffix(suffix)
        return class_name.lower()

    def _get_active_proxy(self) -> str:
        """Get the currently configured proxy type."""
        # HOP3_PROXY_TYPE is a str constant; .lower() cannot fail. The
        # try/except that used to wrap this guarded nothing.
        return HOP3_PROXY_TYPE.lower()

    def _get_detected_os(self, pm: PluginManager) -> str | None:
        """
        Get the detected OS for this system, or None if no plugin claims it.

        A detect() that raises is reported rather than swallowed: "no OS
        plugin matched" and "the matching OS plugin is broken" need different
        fixes, and this output is where an operator goes to tell them apart.
        """
        for os_list in pm.hook.get_os_implementations():
            for os_class in os_list:
                os_instance = os_class()
                if not hasattr(os_instance, "detect"):
                    continue
                try:
                    detected = os_instance.detect()
                except Exception as e:
                    echo(
                        f"Warning: {os_class.__name__}.detect() failed: "
                        f"{type(e).__name__}: {e}",
                        fg="red",
                    )
                    continue
                if detected:
                    return getattr(os_class, "name", os_class.__name__.lower())
        return None

    def _print_verbose(self, pm: PluginManager) -> None:
        """Print detailed information about each plugin, grouped by category."""
        plugins = list(pm.get_plugins())
        plugins_with_hooks = [p for p in plugins if pm.get_hookcallers(p)]
        filtered_plugins = self._filter_redundant_plugins(plugins_with_hooks)

        # Skip internal/core plugins
        user_plugins = [p for p in filtered_plugins if not self._is_internal_plugin(p)]

        # Categorize plugins
        categorized = self._categorize_plugins(pm, user_plugins)

        title = f"Registered Plugins ({len(user_plugins)})"
        print(bold(title))
        print("=" * len(title))

        # Print in logical order
        category_order = ["Build", "Deploy", "Proxy", "OS", "Addons", "Other"]
        for category in category_order:
            if category not in categorized:
                continue

            header = f"{category}:"
            print(f"\n{bold(header)}")
            print("-" * len(header))
            for plugin in sorted(categorized[category], key=self._get_plugin_name):
                self._print_plugin_details(pm, plugin)

    def _categorize_plugins(self, pm: PluginManager, plugins: list) -> dict[str, list]:
        """Categorize plugins based on the hooks they implement."""
        # Hook to category mapping
        hook_categories = {
            "get_builders": "Build",
            "get_language_toolchains": "Build",
            "get_deployers": "Deploy",
            "get_proxies": "Proxy",
            "get_os_implementations": "OS",
            "get_addons": "Addons",
        }

        categorized: dict[str, list] = {}

        for plugin in plugins:
            hook_impls = pm.get_hookcallers(plugin)
            category = "Other"

            if hook_impls:
                for hook_caller in hook_impls:
                    hook_name = hook_caller.name
                    if hook_name in hook_categories:
                        category = hook_categories[hook_name]
                        break

            if category not in categorized:
                categorized[category] = []
            categorized[category].append(plugin)

        return categorized

    def _is_internal_plugin(self, plugin: types.ModuleType | _Named) -> bool:
        """Check if this is an internal plugin that shouldn't be shown."""
        name = self._get_plugin_name(plugin)
        return name == "core"

    def _get_plugin_name(self, plugin: types.ModuleType | _Named) -> str:
        """Get the display name for a plugin."""
        if isinstance(plugin, types.ModuleType):
            parts = plugin.__name__.split(".")
            if "plugins" in parts:
                idx = parts.index("plugins")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
            return parts[-1]
        # All plugin classes implement a Protocol with name: str
        return plugin.name

    def _filter_redundant_plugins(self, plugins: list) -> list:
        """Filter out module-level plugins when a class-based plugin exists."""
        result = []
        seen_modules = set()

        for plugin in plugins:
            if not isinstance(plugin, types.ModuleType):
                seen_modules.add(plugin.__class__.__module__)

        for plugin in plugins:
            if isinstance(plugin, types.ModuleType):
                if plugin.__name__ not in seen_modules:
                    result.append(plugin)
            else:
                result.append(plugin)

        return result

    def _print_plugin_details(
        self, pm: PluginManager, plugin: types.ModuleType | _Named
    ) -> None:
        """Print detailed information about a single plugin."""
        name = self._get_plugin_name(plugin)

        if isinstance(plugin, types.ModuleType):
            path = plugin.__name__
            doc = (plugin.__doc__ or "").strip().split("\n")[0]
        else:
            plugin_class = plugin.__class__
            path = f"{plugin_class.__module__}.{plugin_class.__name__}"
            doc = (plugin_class.__doc__ or "").strip().split("\n")[0]

        print(f"\n{bold(name)}")
        print(f"  Path: {dim(path)}")
        if doc:
            print(f"  {doc}")

        # Show what this plugin provides
        hook_impls = pm.get_hookcallers(plugin)
        if hook_impls:
            for hook_caller in hook_impls:
                hook_name = hook_caller.name
                if hook_name in STRATEGY_HOOKS:
                    method = getattr(plugin, hook_name, None)
                    if method:
                        items = method()
                        if items:
                            item_names: list[str] = [
                                getattr(s, "name", None) or s.__name__ for s in items
                            ]
                            label = self._get_hook_label(hook_name)
                            print(f"  {label}: {', '.join(item_names)}")

    def _get_hook_label(self, hook_name: str) -> str:
        """Get a short label for a hook."""
        labels = {
            "get_builders": "Builders",
            "get_deployers": "Deployers",
            "get_language_toolchains": "Toolchains",
            "get_proxies": "Proxies",
            "get_os_implementations": "OS",
            "get_addons": "Addons",
        }
        return labels.get(hook_name, hook_name)
