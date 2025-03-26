# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import attrs
from starlette.applications import Starlette
from starlette.routing import Route

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

DEBUG = True


@attrs.frozen
class SetupContext:
    routes: list = attrs.Factory(list)

    def add_route(
        self,
        path: str,
        endpoint: Callable[[Request], Awaitable[Response] | Response],
        methods: list[str] | None = None,
        name: str | None = None,
        *,
        include_in_schema: bool = True,
    ) -> None:
        # copy/pasted from Starlette
        route = Route(
            path,
            endpoint=endpoint,
            methods=methods,
            name=name,
            include_in_schema=include_in_schema,
        )
        self.routes.append(route)


def create_app():
    from . import views

    ctx = SetupContext()
    views.setup(ctx)
    routes = ctx.routes

    return Starlette(debug=DEBUG, routes=routes)
