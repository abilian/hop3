# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard addons controller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from litestar import Controller, get
from litestar.response import Redirect, Template

from hop3.core.plugins import get_addon
from hop3.orm import AddonCredentialRepository
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session

if TYPE_CHECKING:
    from litestar.params import FromPath


class AddonsController(Controller):
    """Controller for addon management routes."""

    path = "/dashboard/addons"
    guards = [auth_guard]  # noqa: RUF012

    @get("/", sync_to_thread=False)
    def dashboard_addons(self) -> Template | Redirect:
        """Display addons page."""
        with get_session() as db_session:
            addon_credential_repo = AddonCredentialRepository(session=db_session)
            credentials = addon_credential_repo.list_all_with_apps()

            addons = []
            for cred in credentials:
                addons.append({
                    "id": cred.id,
                    "app_name": cred.app.name,
                    "addon_type": cred.addon_type,
                    "addon_name": cred.addon_name,
                    "created_at": cred.created_at.strftime("%Y-%m-%d %H:%M")
                    if cred.created_at
                    else "N/A",
                })

        ctx = {"addons": addons}
        return Template(template_name="dashboard/addons.html", context=ctx)

    @get("/{addon_name:str}", sync_to_thread=False)
    def addon_detail(self, addon_name: FromPath[str]) -> Template:
        """Display addon detail page."""
        with get_session() as db_session:
            addon_credential_repo = AddonCredentialRepository(session=db_session)
            credential = addon_credential_repo.get_by_addon_name(addon_name)

            if not credential:
                return Template(
                    template_name="dashboard/error.html",
                    context={
                        "error_title": "Addon Not Found",
                        "error_message": f"Addon '{addon_name}' does not exist.",
                    },
                    status_code=404,
                )

            app = credential.app

            try:
                addon = get_addon(credential.addon_type, addon_name)
                connection_details = addon.get_connection_details()
                info = addon.info()
            except Exception as e:
                connection_details = {}
                info = {"error": str(e)}

            addon_data = {
                "addon_name": credential.addon_name,
                "addon_type": credential.addon_type,
                "app_name": app.name,
                "created_at": credential.created_at.strftime("%Y-%m-%d %H:%M")
                if credential.created_at
                else "N/A",
            }

        ctx = {
            "addon": addon_data,
            "connection_details": connection_details,
            "info": info,
        }
        return Template(template_name="dashboard/addon_detail.html", context=ctx)
