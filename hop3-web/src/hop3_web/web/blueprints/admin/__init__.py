# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from flask import Blueprint

blueprint = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates",
    static_folder="static",
    static_url_path="",
)

# blueprint.before_request(ensure_admin)
route = blueprint.route
get = blueprint.get
post = blueprint.post
