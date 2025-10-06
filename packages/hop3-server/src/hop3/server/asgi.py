# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import (
    AuthenticationMiddleware as StarletteAuthMiddleware,
)

from .lib.scanner import scan_package
from .middleware.auth import BearerTokenBackend
from .singletons import router

if TYPE_CHECKING:
    pass

DEBUG = True


def create_app():
    scan_package("hop3.server.views")
    routes = list(router)

    # Add authentication middleware if enabled
    # Read from environment to support test fixtures that set env vars
    enable_auth = os.environ.get("HOP3_ENABLE_AUTH", "true").lower() in {
        "true",
        "1",
        "yes",
    }
    middleware = []
    if enable_auth:
        middleware.append(
            Middleware(StarletteAuthMiddleware, backend=BearerTokenBackend())
        )

    return Starlette(debug=DEBUG, routes=routes, middleware=middleware)
