# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard addons controller."""

from __future__ import annotations

import anyio
from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, get

# Runtime imports: `@inject` resolves the handler annotations when it wraps them.
from litestar.params import FromPath  # ruff:ignore[typing-only-third-party-import]
from litestar.response import Redirect, Template

from hop3.core.plugins import get_addon
from hop3.core.roles import Role
from hop3.orm import (  # ruff:ignore[typing-only-first-party-import]
    AddonCredentialRepository,
)
from hop3.server.guards import RoleGuard


class AddonsController(Controller):
    """Controller for addon management routes."""

    path = "/dashboard/addons"
    guards = [RoleGuard(Role.VIEWER)]  # ruff:ignore[mutable-class-default]

    @get("/")
    @inject
    async def dashboard_addons(
        self, addon_repo: FromDishka[AddonCredentialRepository]
    ) -> Template | Redirect:
        """Display addons page."""
        return await anyio.to_thread.run_sync(self._addons, addon_repo)

    @staticmethod
    def _addons(addon_repo: AddonCredentialRepository) -> Template:
        addons = [
            {
                "id": cred.id,
                "app_name": cred.app.name,
                "addon_type": cred.addon_type,
                "addon_name": cred.addon_name,
                "created_at": cred.created_at.strftime("%Y-%m-%d %H:%M")
                if cred.created_at
                else "N/A",
            }
            for cred in addon_repo.list_all_with_apps()
        ]
        return Template(
            template_name="dashboard/addons.html", context={"addons": addons}
        )

    @get("/{addon_name:str}", guards=[RoleGuard(Role.DEPLOYER)])
    @inject
    async def addon_detail(
        self,
        addon_name: FromPath[str],
        addon_repo: FromDishka[AddonCredentialRepository],
    ) -> Template:
        """Display addon detail page (``info()`` opens a connection to the addon)."""
        return await anyio.to_thread.run_sync(self._detail, addon_repo, addon_name)

    @staticmethod
    def _detail(addon_repo: AddonCredentialRepository, addon_name: str) -> Template:
        credential = addon_repo.get_by_addon_name(addon_name)
        if not credential:
            return Template(
                template_name="dashboard/error.html",
                context={
                    "error_title": "Addon Not Found",
                    "error_message": f"Addon '{addon_name}' does not exist.",
                },
                status_code=404,
            )

        try:
            addon = get_addon(credential.addon_type, addon_name)
            connection_details = addon.get_connection_details()
            info = addon.info()
        except Exception as e:
            connection_details = {}
            info = {"error": str(e)}

        ctx = {
            "addon": {
                "addon_name": credential.addon_name,
                "addon_type": credential.addon_type,
                "app_name": credential.app.name,
                "created_at": credential.created_at.strftime("%Y-%m-%d %H:%M")
                if credential.created_at
                else "N/A",
            },
            "connection_details": connection_details,
            "info": info,
        }
        return Template(template_name="dashboard/addon_detail.html", context=ctx)
