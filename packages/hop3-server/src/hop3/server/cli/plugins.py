# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import types
from argparse import ArgumentParser

from hop3.config import HOP3_PROXY_TYPE
from hop3.core.plugins import get_plugin_manager
from hop3.lib.console import bold, dim, green
from hop3.lib.registry import register
from hop3.server.asgi import create_app

from . import Command

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

    def run(self, *, verbose_plugins: bool = False):
        app = create_app()
        pm = get_plugin_manager()

        if verbose_plugins:
            self._print_verbose(pm)
        else:
            self._print_summary(pm)

    def _print_summary(self, pm) -> None:
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

    def _gather_capabilities(self, pm) -> dict[str, set[str]]:
        """Gather all capabilities from registered plugins."""
        capabilities: dict[str, set[str]] = {
            "builders": set(),
            "deployers": set(),
            "toolchains": set(),
            "proxies": set(),
            "os_support": set(),
            "addons": set(),
        }

        self._gather_builders(pm, capabilities)
        self._gather_deployers(pm, capabilities)
        self._gather_toolchains(pm, capabilities)
        self._gather_proxies(pm, capabilities)
        self._gather_os_support(pm, capabilities)
        self._gather_addons(pm, capabilities)

        return capabilities

    def _gather_builders(self, pm, capabilities: dict[str, set[str]]) -> None:
        """Gather builder capabilities from plugins."""
        try:
            for builder_list in pm.hook.get_builders():
                for builder in builder_list:
                    name = getattr(builder, "name", builder.__name__)
                    if name != "dummy":
                        capabilities["builders"].add(name)
        except Exception:
            pass

    def _gather_deployers(self, pm, capabilities: dict[str, set[str]]) -> None:
        """Gather deployer capabilities from plugins."""
        try:
            for deployer_list in pm.hook.get_deployers():
                for deployer in deployer_list:
                    name = getattr(deployer, "name", deployer.__name__)
                    if name != "dummy":
                        capabilities["deployers"].add(name)
        except Exception:
            pass

    def _gather_toolchains(self, pm, capabilities: dict[str, set[str]]) -> None:
        """Gather toolchain capabilities from plugins."""
        try:
            for toolchain_list in pm.hook.get_language_toolchains():
                for toolchain in toolchain_list:
                    name = getattr(toolchain, "name", toolchain.__name__)
                    lang_name = self._toolchain_to_language(name)
                    if lang_name:
                        capabilities["toolchains"].add(lang_name)
        except Exception:
            pass

    def _gather_proxies(self, pm, capabilities: dict[str, set[str]]) -> None:
        """Gather proxy capabilities from plugins."""
        try:
            for proxy_list in pm.hook.get_proxies():
                for proxy in proxy_list:
                    name = self._extract_proxy_name(proxy)
                    capabilities["proxies"].add(name)
        except Exception:
            pass

    def _gather_os_support(self, pm, capabilities: dict[str, set[str]]) -> None:
        """Gather OS support capabilities from plugins."""
        try:
            for os_list in pm.hook.get_os_implementations():
                for os_impl in os_list:
                    name = getattr(os_impl, "name", os_impl.__name__.lower())
                    capabilities["os_support"].add(name)
        except Exception:
            pass

    def _gather_addons(self, pm, capabilities: dict[str, set[str]]) -> None:
        """Gather addon capabilities from plugins."""
        try:
            for addon_list in pm.hook.get_addons():
                for addon in addon_list:
                    name = getattr(addon, "name", addon.__name__.lower())
                    capabilities["addons"].add(name)
        except Exception:
            pass

    def _toolchain_to_language(self, toolchain_name: str) -> str | None:
        """Convert toolchain name to user-friendly language name.

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

    def _extract_proxy_name(self, proxy_class) -> str:
        """Extract clean proxy name from class."""
        # First try explicit name attribute
        if hasattr(proxy_class, "name"):
            return proxy_class.name

        # Extract from class name (e.g., NginxVirtualHost -> nginx)
        class_name = proxy_class.__name__
        # Remove common suffixes
        for suffix in ["VirtualHost", "Proxy", "Strategy"]:
            class_name = class_name.removesuffix(suffix)
        return class_name.lower()

    def _get_active_proxy(self) -> str | None:
        """Get the currently configured proxy type."""
        try:
            return HOP3_PROXY_TYPE.lower()
        except Exception:
            return None

    def _get_detected_os(self, pm) -> str | None:
        """Get the detected OS for this system."""
        try:
            for os_list in pm.hook.get_os_implementations():
                for os_class in os_list:
                    os_instance = os_class()
                    if hasattr(os_instance, "detect") and os_instance.detect():
                        return getattr(os_class, "name", os_class.__name__.lower())
        except Exception:
            pass
        return None

    def _print_verbose(self, pm) -> None:
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

    def _categorize_plugins(self, pm, plugins: list) -> dict[str, list]:
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

    def _is_internal_plugin(self, plugin) -> bool:
        """Check if this is an internal plugin that shouldn't be shown."""
        name = self._get_plugin_name(plugin)
        return name == "core"

    def _get_plugin_name(self, plugin) -> str:
        """Get the display name for a plugin."""
        if isinstance(plugin, types.ModuleType):
            parts = plugin.__name__.split(".")
            if "plugins" in parts:
                idx = parts.index("plugins")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
            return parts[-1]
        return getattr(plugin, "name", plugin.__class__.__name__.lower())

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

    def _print_plugin_details(self, pm, plugin) -> None:
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
                            item_names = [getattr(s, "name", s.__name__) for s in items]
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
