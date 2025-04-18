# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.applications import Starlette

from .lib.scanner import scan_package
from .singletons import router

if TYPE_CHECKING:
    pass

DEBUG = True


def create_app():
    scan_package("hop3.server.views")
    routes = list(router)
    return Starlette(debug=DEBUG, routes=routes)
