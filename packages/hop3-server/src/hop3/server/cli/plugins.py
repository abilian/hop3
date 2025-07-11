# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from hop3.lib.registry import register
from hop3.server.asgi import create_app

from . import Command
from hop3.core.plugins import get_plugin_manager


@register
class Plugins(Command):
    """Lists all plugins."""

    name = "plugins"

    def run(self):
        app = create_app()
        self._list_plugins(app)

    def _list_plugins(self, app):
        pm = get_plugin_manager()
        print("Registered plugins:")
        for plugin in pm.get_plugins():
            print(f"- {plugin.name} ({plugin.__class__.__module__}.{plugin.__class__.__name__})")
