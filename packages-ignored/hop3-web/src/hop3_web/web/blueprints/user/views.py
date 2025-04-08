# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

import wrapt
from flask import render_template
from wireup import Injected

from hop3_web.services.database_connection import DatabaseConnection
from hop3_web.web.menus import MAIN_MENU

from . import get


def templated(template_name: str):
    """Decorator to render a template."""

    @wrapt.decorator
    def wrapper(wrapped, instance, args, kwargs):
        context = wrapped(*args, **kwargs)
        return render_template(template_name, **context)

    return wrapper


@get("/")
@templated("user/index.html")
def home(conn: Injected[DatabaseConnection]):
    """Serve site root."""

    _session = conn.session
    apps = []
    ctx = {
        "main_menu": MAIN_MENU,
        "apps": apps,
    }
    return ctx
