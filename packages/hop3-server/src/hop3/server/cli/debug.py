# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from hop3 import config as config_module
from hop3.lib.registry import register
from hop3.server.asgi import create_app

from . import Command


@register
class Routes(Command):
    """Lists all routes."""

    name = "routes"

    def run(self):
        app = create_app()
        self._list_routes(app)

    def _list_routes(self, app, level=0):
        prefix = "  " * level
        if isinstance(app, StaticFiles):
            print(
                f"{prefix}StaticFiles | directory: {app.directory}, packages: {app.packages}, directories: {app.all_directories}"
            )
            return

        if not hasattr(app, "routes"):
            return

        for route in app.routes:
            match route:
                case Route():
                    print(
                        f"{prefix}Route | Path: {route.path}, Name: {route.name}, Methods: {', '.join(route.methods or [])}"
                    )
                case Mount():
                    print(
                        f"{prefix}Mount | Path: {route.path}, Name: {route.name}, Mounted App: {route.app}"
                    )
                    self._list_routes(route.app, level + 1)
                case _:
                    print(f"{prefix}Unknown route: {route}")


@register
class Config(Command):
    """Prints the configuration."""

    def run(self):
        for key in sorted(vars(config_module)):
            if key.isupper():
                print(f"{key}: {getattr(config_module, key)!r}")
