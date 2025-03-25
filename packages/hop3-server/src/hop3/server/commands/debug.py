# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from hop3.lib.decorators import command
from hop3.server.asgi import create_app

# import app.config as config_module
# from app.lib.decorators import command
# from app.server import serve


@command
def run():
    """Runs the server."""
    print("Running server")
    serve()


@command
def routes():
    """Lists all routes."""
    app = create_app()
    _list_routes(app)


@command
def config():
    """Prints the configuration."""
    for key in sorted(vars(config_module)):
        if key.isupper():
            print(f"{key}: {getattr(config_module, key)!r}")
        # if config_object.get(key, default=None) is not None:
        #     print(f"{key}: {config_object.get(key)}")


def _list_routes(app, level=0):
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
                _list_routes(route.app, level + 1)
            case _:
                print(f"{prefix}Unknown route: {route}")
