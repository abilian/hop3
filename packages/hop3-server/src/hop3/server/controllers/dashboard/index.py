# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard index controller."""

from __future__ import annotations

from litestar import Controller, get
from litestar.response import Template

from hop3.orm import App
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session

from .helpers import get_app_state_dict


class DashboardIndexController(Controller):
    """Main dashboard index controller."""

    path = "/dashboard"
    guards = [auth_guard]  # noqa: RUF012

    @get("/", status_code=200, sync_to_thread=False)
    def dashboard_index(self) -> Template:
        """Display the main dashboard with application list."""
        with get_session() as db_session:
            apps_list = db_session.query(App).order_by(App.name).all()

            app_list = [
                {
                    "name": app.name,
                    "state": get_app_state_dict(app),
                    "port": app.port,
                    "created_at": app.created_at.isoformat()
                    if app.created_at
                    else None,
                }
                for app in apps_list
            ]

        ctx = {"apps": app_list}
        return Template(template_name="dashboard/index.html", context=ctx)
