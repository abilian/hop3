# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from flask import render_template
from markupsafe import Markup
from prettyprinter import pformat
from webbits.html import html

from hop3_web.web.menus import ADMIN_MENU, MAIN_MENU

from . import get


@get("/")
def home() -> str:
    result = []

    body = h = html()
    with h.div(class_="content ~neutral"):
        h.h2("Apps")
        with h.ul():
            for instance in result:
                site_config = instance["site_config"]
                metadata = site_config["image_nua_config"]["metadata"]
                url = f"/admin/apps/{instance['app_id']}/"
                title = metadata["title"]
                # Should be: h.li(h.a(title, href=url))
                with h.li():
                    h.a(title, href=url)

    ctx = {
        "main_menu": MAIN_MENU,
        "admin_menu": ADMIN_MENU,
        "title": "Admin",
        "body": Markup(str(body)),
    }

    return render_template("admin/index.html", **ctx)


@get("/settings/")
def settings_view(self) -> str:
    result = []

    body = h = html()
    with h.div(class_="content ~neutral"):
        h.h2("Raw output")
        h.pre(json_pp(result))

    ctx = {
        "main_menu": MAIN_MENU,
        "admin_menu": ADMIN_MENU,
        "title": "Settings",
        "body": Markup(str(body)),
    }
    return render_template("admin/index3.html", **ctx)


@get("/apps/<app_id>/")
def app_view(app_id: str) -> str:
    app_info = get_app_info(app_id)

    body = h = html()
    with h.div(class_="content ~neutral"):
        h.h2("Raw output")
        h.pre(json_pp(app_info))

    ctx = {
        "main_menu": MAIN_MENU,
        "admin_menu": ADMIN_MENU,
        "title": f"App: {app_id}",
        "body": Markup(str(body)),
    }
    return render_template("admin/app.html", **ctx)


@get("/apps/<app_id>/logs/")
def app_logs_view(app_id: str) -> str:
    app_info = get_app_info(app_id)

    body = h = html()
    with h.div(class_="content ~neutral"):
        h.h2("Raw output")
        h.pre(json_pp(app_info))

    ctx = {
        "main_menu": MAIN_MENU,
        "admin_menu": ADMIN_MENU,
        "title": f"App: {app_id}",
        "body": Markup(str(body)),
    }
    return render_template("admin/app_logs.html", **ctx)


#
# Utils
#
def get_app_info(app_id: str) -> dict:
    # client = get_client()
    # result = client.call("list")

    result = []

    app = None
    for instance in result:
        if instance["app_id"] == app_id:
            app = instance
            break

    return app


def json_pp(obj):
    return pformat(obj, indent=4, sort_dict_keys=True)
