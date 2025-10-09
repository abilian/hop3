# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import types
from argparse import ArgumentParser

from hop3.core.plugins import get_plugin_manager
from hop3.lib.registry import register
from hop3.server.asgi import create_app

from . import Command

# Strategy hooks that provide lists of strategies
STRATEGY_HOOKS = {
    "get_build_strategies",
    "get_deployment_strategies",
    "get_service_strategies",
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

    def run(self, verbose_plugins: bool = False):
        app = create_app()
        self._list_plugins(app, verbose_plugins)

    def _list_plugins(self, app, verbose: bool = False):
        pm = get_plugin_manager()
        plugins = list(pm.get_plugins())

        # Filter out module plugins that have no hooks (just imported for side effects)
        plugins_with_hooks = [p for p in plugins if pm.get_hookcallers(p)]

        if not verbose:
            # Simple listing
            print("Registered plugins:")
            for plugin in plugins_with_hooks:
                plugin_info = self._get_plugin_info(plugin)
                print(f"- {plugin_info['name']} ({plugin_info['full_path']})")
        else:
            # Detailed listing
            print(f"Registered plugins ({len(plugins_with_hooks)}):\n")
            for plugin in plugins_with_hooks:
                self._print_plugin_details(pm, plugin)
                print()  # Empty line between plugins

    def _get_plugin_info(self, plugin) -> dict[str, str]:
        """Extract plugin information, handling both module and class-based plugins."""

        match plugin:
            case types.ModuleType():
                # Module-based plugin
                return {
                    "name": getattr(plugin, "__name__", "unknown").split(".")[-1],
                    "full_path": plugin.__name__,
                    "doc": plugin.__doc__,
                }
            case _:
                # Class-based plugin
                plugin_class = plugin.__class__
                return {
                    "name": getattr(plugin, "name", plugin_class.__name__),
                    "full_path": f"{plugin_class.__module__}.{plugin_class.__name__}",
                    "doc": plugin_class.__doc__,
                }

    def _print_plugin_details(self, pm, plugin):
        """Print detailed information about a plugin using pluggy's introspection API."""
        plugin_info = self._get_plugin_info(plugin)

        # Header
        print(f"Plugin: {plugin_info['name']}")
        print(f"  Module/Class: {plugin_info['full_path']}")

        # Docstring
        if plugin_info["doc"]:
            doc = plugin_info["doc"].strip().split("\n")[0]  # First line only
            print(f"  Description: {doc}")

        # Use pluggy's API to introspect what hooks this plugin implements
        hook_impls = pm.get_hookcallers(plugin)

        if not hook_impls:
            print("  Capabilities: (none)")
            return

        print("  Capabilities:")
        for hook_caller in hook_impls:
            hook_name = hook_caller.name
            hook_description = self._get_hook_description(pm, hook_name)
            self._print_hook_capability(plugin, hook_name, hook_description)

    def _print_hook_capability(
        self, plugin, hook_name: str, hook_description: str
    ) -> None:
        """Print a single hook capability for a plugin.

        Args:
            plugin: The plugin instance
            hook_name: The name of the hook
            hook_description: Human-readable description of the hook
        """
        # For strategy hooks, show what strategies are provided
        if hook_name in STRATEGY_HOOKS:
            self._print_strategy_hook(plugin, hook_name, hook_description)
        else:
            # For other hooks, just show the description
            print(f"    - {hook_description}")

    def _print_strategy_hook(
        self, plugin, hook_name: str, hook_description: str
    ) -> None:
        """Print strategy hook details with list of strategies.

        Args:
            plugin: The plugin instance
            hook_name: The name of the strategy hook
            hook_description: Human-readable description of the hook
        """
        method = getattr(plugin, hook_name, None)
        if not method:
            print(f"    - {hook_description}: (none configured)")
            return

        strategies = method()
        strategy_names = [getattr(s, "name", s.__name__) for s in strategies]

        if strategy_names:
            print(f"    - {hook_description}: {', '.join(strategy_names)}")
        else:
            print(f"    - {hook_description}: (none configured)")

    def _get_hook_description(self, pm, hook_name: str) -> str:
        """Get a human-readable description of a hook from its hookspec docstring."""
        # Map hook names to user-friendly descriptions
        descriptions = {
            "get_build_strategies": "Provides build strategies",
            "get_deployment_strategies": "Provides deployment strategies",
            "get_service_strategies": "Provides service strategies",
            "cli_commands": "Provides CLI commands",
        }

        return descriptions.get(hook_name, hook_name.replace("_", " ").title())
