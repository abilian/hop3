# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import attrs
from starlette.applications import Starlette

from . import views

# DEBUG = bool(os.environ.get("HOP3_DEBUG", False))
DEBUG = True


@attrs.frozen
class SetupContext:
    routes: list = attrs.Factory(list)


def create_app():
    ctx = SetupContext()
    views.setup(ctx)
    routes = ctx.routes

    return Starlette(debug=DEBUG, routes=routes)
