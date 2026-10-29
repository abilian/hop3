# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard index controller."""

from __future__ import annotations

import anyio
from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, get
from litestar.response import Template

from hop3.core.roles import Role
from hop3.orm import AppRepository  # ruff:ignore[typing-only-first-party-import]
from hop3.server.guards import RoleGuard

from .helpers import get_display_state


class DashboardIndexController(Controller):
    """Main dashboard index controller."""

    path = "/dashboard"
    guards = [RoleGuard(Role.VIEWER)]  # ruff:ignore[mutable-class-default]

    @get("/", status_code=200)
    @inject
    async def dashboard_index(self, app_repo: FromDishka[AppRepository]) -> Template:
        """Display the main dashboard with application list."""
        return await anyio.to_thread.run_sync(self._index, app_repo)

    @staticmethod
    def _index(app_repo: AppRepository) -> Template:
        app_list = [
            {
                "name": app.name,
                "state": get_display_state(app),
                "port": app.port,
                "created_at": app.created_at.isoformat() if app.created_at else None,
            }
            for app in app_repo.list_all_ordered()
        ]
        return Template(
            template_name="dashboard/index.html", context={"apps": app_list}
        )
