# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Service-related dashboard views."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.plugins import get_service_strategy
from hop3.orm import App
from hop3.orm.service_credential import ServiceCredential
from hop3.server.lib.database import get_session
from hop3.server.singletons import router, templates

from .utils import require_auth

if TYPE_CHECKING:
    from starlette.requests import Request


@router.get("/dashboard/services")
@require_auth
def dashboard_services(request: Request):
    """Display services page.

    Args:
        request: The HTTP request

    Returns:
        Template response with services list
    """
    # Get all service credentials from database
    with get_session() as db_session:
        credentials = db_session.query(ServiceCredential).join(App).all()

        # Convert to dict for template
        services = []
        for cred in credentials:
            services.append({
                "id": cred.id,
                "app_name": cred.app.name,
                "service_type": cred.service_type,
                "service_name": cred.service_name,
                "created_at": cred.created_at.strftime("%Y-%m-%d %H:%M")
                if cred.created_at
                else "N/A",
            })

    ctx = {"services": services}
    return templates(request, "dashboard/services.html", ctx)


@router.get("/dashboard/services/{service_name}")
@require_auth
def service_detail(request: Request):
    """Display service detail page.

    Args:
        request: The HTTP request

    Returns:
        Template response with service details
    """
    service_name = request.path_params["service_name"]

    # Get service credential from database
    with get_session() as db_session:
        credential = (
            db_session.query(ServiceCredential)
            .filter(ServiceCredential.service_name == service_name)
            .first()
        )

        if not credential:
            # Service not found
            return templates(
                request,
                "dashboard/error.html",
                {
                    "error_title": "Service Not Found",
                    "error_message": f"Service '{service_name}' does not exist.",
                },
                status_code=404,
            )

        # Get app name for the service
        app = credential.app

        # Get service strategy and connection details
        try:
            service = get_service_strategy(credential.service_type, service_name)
            connection_details = service.get_connection_details()
            info = service.info()
        except Exception as e:
            connection_details = {}
            info = {"error": str(e)}

        service_data = {
            "service_name": credential.service_name,
            "service_type": credential.service_type,
            "app_name": app.name,
            "created_at": credential.created_at.strftime("%Y-%m-%d %H:%M")
            if credential.created_at
            else "N/A",
        }

    ctx = {
        "service": service_data,
        "connection_details": connection_details,
        "info": info,
    }
    return templates(request, "dashboard/service_detail.html", ctx)
