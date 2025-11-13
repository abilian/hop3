# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard views package.

This package organizes dashboard views into logical modules:
- apps: Application-related views
- services: Service management views
- backups: Backup and restore views
- utils: Shared utilities and decorators
- db_helpers: Database helper functions
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse

from hop3.orm import App
from hop3.server.lib.database import get_session
from hop3.server.singletons import router, templates

# Import submodules to register routes
from . import apps, backups, services
from .db_helpers import get_app_state_dict
from .utils import is_authenticated, require_auth

if TYPE_CHECKING:
    from starlette.requests import Request

__all__ = ["apps", "backups", "services"]


@router.get("/")
def index(request: Request):
    """Redirect root to dashboard.

    Args:
        request: The HTTP request

    Returns:
        Redirect to dashboard or login
    """
    if is_authenticated(request):
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/auth/login", status_code=302)


@router.get("/dashboard")
@require_auth
def dashboard_index(request: Request):
    """Display the main dashboard with application list.

    Args:
        request: The HTTP request

    Returns:
        Template response with application list
    """
    # Get all applications
    with get_session() as db_session:
        apps_list = db_session.query(App).order_by(App.name).all()

        # Convert to dict for template
        app_list = [
            {
                "name": app.name,
                "state": get_app_state_dict(app),
                "port": app.port,
                "created_at": app.created_at.isoformat() if app.created_at else None,
            }
            for app in apps_list
        ]

    ctx = {"apps": app_list}
    return templates(request, "dashboard/index.html", ctx)
