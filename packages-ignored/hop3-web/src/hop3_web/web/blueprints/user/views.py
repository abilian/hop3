# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from flask import render_template

from hop3_web.web.menus import MAIN_MENU

from . import get


@get("/")
def home():
    """Serve site root."""

    apps = []
    ctx = {
        "main_menu": MAIN_MENU,
        "apps": apps,
    }
    return render_template("user/index.html", **ctx)
