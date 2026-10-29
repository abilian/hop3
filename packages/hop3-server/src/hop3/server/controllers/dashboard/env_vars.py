# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard environment variables controller."""

from __future__ import annotations

from operator import itemgetter

import anyio
from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, get

# Runtime import (not TYPE_CHECKING): Litestar resolves the FromPath path-param
# annotation at route registration via get_type_hints, so it must exist at runtime.
from litestar.params import FromPath  # ruff:ignore[typing-only-third-party-import]
from litestar.response import Redirect, Template

from hop3.core.roles import Role
from hop3.orm import AppRepository  # ruff:ignore[typing-only-first-party-import]
from hop3.server.guards import RoleGuard

from .helpers import is_service_var


class EnvVarsController(Controller):
    """Controller for app environment variable routes."""

    path = "/dashboard/apps/{app_name:str}/env"
    guards = [RoleGuard(Role.DEPLOYER)]  # ruff:ignore[mutable-class-default]

    @get("/")
    @inject
    async def app_env_vars(
        self, app_name: FromPath[str], app_repo: FromDishka[AppRepository]
    ) -> Template | Redirect:
        """Display application environment variables page."""
        return await anyio.to_thread.run_sync(self._env_vars, app_repo, app_name)

    @staticmethod
    def _env_vars(app_repo: AppRepository, app_name: str) -> Template | Redirect:
        app = app_repo.get_by_name(app_name)
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
