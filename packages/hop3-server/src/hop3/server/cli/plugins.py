# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from argparse import ArgumentParser

from hop3.core.plugins import get_plugin_manager
from hop3.lib.registry import register
from hop3.server.asgi import create_app

from . import Command


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

        if not verbose:
            # Simple listing
            print("Registered plugins:")
            for plugin in plugins:
                plugin_name = getattr(plugin, "name", plugin.__class__.__name__)
                print(
                    f"- {plugin_name} ({plugin.__class__.__module__}.{plugin.__class__.__name__})"
                )
        else:
            # Detailed listing
            print(f"Registered plugins ({len(plugins)}):\n")
            for plugin in plugins:
                self._print_plugin_details(plugin)
                print()  # Empty line between plugins

    def _print_plugin_details(self, plugin):
        """Print detailed information about a plugin."""
        plugin_name = getattr(plugin, "name", plugin.__class__.__name__)
        plugin_class = plugin.__class__
        plugin_module = plugin_class.__module__
        plugin_class_name = plugin_class.__name__

        # Header
        print(f"Plugin: {plugin_name}")
        print(f"  Class: {plugin_module}.{plugin_class_name}")

        # Docstring
        if plugin_class.__doc__:
            doc = plugin_class.__doc__.strip().split("\n")[0]  # First line only
            print(f"  Description: {doc}")

        # Check what hooks this plugin implements
        hooks = []

        if hasattr(plugin, "get_build_strategies"):
            try:
                strategies = plugin.get_build_strategies()
                strategy_names = [
                    getattr(s, "name", s.__name__) for s in strategies
                ]
                hooks.append(f"Build strategies: {', '.join(strategy_names)}")
            except Exception:
                hooks.append("Build strategies: <error retrieving>")

        if hasattr(plugin, "get_deployment_strategies"):
            try:
                strategies = plugin.get_deployment_strategies()
                strategy_names = [
                    getattr(s, "name", s.__name__) for s in strategies
                ]
                hooks.append(f"Deployment strategies: {', '.join(strategy_names)}")
            except Exception:
                hooks.append("Deployment strategies: <error retrieving>")

        if hasattr(plugin, "get_service_strategies"):
            try:
                strategies = plugin.get_service_strategies()
                strategy_names = [
                    getattr(s, "name", s.__name__) for s in strategies
                ]
                hooks.append(f"Service strategies: {', '.join(strategy_names)}")
            except Exception:
                hooks.append("Service strategies: <error retrieving>")

        if hooks:
            print("  Provides:")
            for hook in hooks:
                print(f"    - {hook}")
        else:
            print("  Provides: (no strategies registered)")
