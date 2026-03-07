# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard environment variables controller."""

from __future__ import annotations

from operator import itemgetter

from litestar import Controller, get
from litestar.response import Redirect, Template

from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session

from .helpers import get_app_or_none, is_service_var


class EnvVarsController(Controller):
    """Controller for app environment variable routes."""

    path = "/dashboard/apps/{app_name:str}/env"
    guards = [auth_guard]  # noqa: RUF012

    @get("/", sync_to_thread=False)
    def app_env_vars(self, app_name: str) -> Template | Redirect:
        """Display application environment variables page."""
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            env_vars = []
            service_var_count = 0

            for env_var in app.env_vars:
                is_service = is_service_var(env_var.name)
                if is_service:
                    service_var_count += 1

                env_vars.append({
                    "name": env_var.name,
                    "value": env_var.value,
                    "is_service": is_service,
                    "description": None,
                })

            env_vars.sort(key=itemgetter("name"))

            ctx = {
                "app_name": app.name,
                "env_vars": env_vars,
                "service_var_count": service_var_count,
            }

        return Template(template_name="dashboard/env_vars.html", context=ctx)
