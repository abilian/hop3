# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


class Router:
    """Decorator factory that generates paths for starlette with the use of
    decorators.

    Yields:
        Route: starlette Route objects
    """

    def __init__(self) -> None:
        self._routes = {}

    def method(self, name):
        def decorator(path: str | None = None):
            def inner(func):
                fname = func.__name__
                if fname in self._routes:
                    self._routes[fname].methods.add(name.upper())
                else:
                    self._routes[fname] = Route(path, func, methods=[name])

                return func

            return inner

        return decorator

    def get(self, path: str | None = None):
        return self.method("GET")(path)

    def post(self, path: str | None = None):
        return self.method("POST")(path)

    def put(self, path: str | None = None):
        return self.method("PUT")(path)

    def delete(self, path: str | None = None):
        return self.method("DELETE")(path)

    def patch(self, path: str | None = None):
        return self.method("PATCH")(path)

    def options(self, path: str | None = None):
        return self.method("OPTIONS")(path)

    def head(self, path: str | None = None):
        return self.method("HEAD")(path)

    def __iter__(self):
        for route in (r := self._routes):
            yield r[route]

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
        _route = Route(
            path,
            endpoint=endpoint,
            methods=methods,
            name=name,
            include_in_schema=include_in_schema,
        )
        # TODO
        if name in self._routes:
            self._routes[name].methods.add(name.upper())
        else:
            self._routes[name] = Route(path, endpoint, methods=[name])
        # self._routes[name.append(route)
