# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard views for the web UI."""

from __future__ import annotations

from datetime import datetime, timezone
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse, Response

from hop3.orm import App
from hop3.project.config import AppConfig
from hop3.server.lib.database import get_session
from hop3.server.singletons import router, templates

if TYPE_CHECKING:
    from starlette.requests import Request


@router.get("/")
def index(request: Request):
    """Redirect root to dashboard.

    Args:
        request: The HTTP request

    Returns:
        Redirect to dashboard or login
    """
    if request.user.is_authenticated:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/auth/login", status_code=302)


@router.get("/dashboard")
def dashboard_index(request: Request):
    """Display the main dashboard with application list.

    Args:
        request: The HTTP request

    Returns:
        Template response with application list
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Get all applications
    with get_session() as db_session:
        apps = db_session.query(App).order_by(App.name).all()

        # Convert to dict for template
        app_list = [
            {
                "name": app.name,
                "state": app.run_state.value if hasattr(app.run_state, "value") else str(app.run_state),
                "port": app.port,
                "created_at": app.created_at,
            }
            for app in apps
        ]

    ctx = {"apps": app_list}
    return templates(request, "dashboard/index.html", ctx)


@router.get("/dashboard/services")
def dashboard_services(request: Request):
    """Display services page (placeholder).

    Args:
        request: The HTTP request

    Returns:
        Template response with services list
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    ctx = {"services": []}  # Placeholder
    return templates(request, "dashboard/services.html", ctx)


@router.get("/dashboard/backups")
def dashboard_backups(request: Request):
    """Display backups page (placeholder).

    Args:
        request: The HTTP request

    Returns:
        Template response with backups list
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    ctx = {"backups": []}  # Placeholder
    return templates(request, "dashboard/backups.html", ctx)


@router.get("/dashboard/apps/{app_name}")
def app_detail(request: Request):
    """Display application detail page.

    Args:
        request: The HTTP request

    Returns:
        Template response with app details
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    app_name = request.path_params["app_name"]

    # Get application from database
    with get_session() as db_session:
        app = db_session.query(App).filter_by(name=app_name).first()

        if not app:
            # App not found, redirect to dashboard
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get workers from AppConfig if app path exists
        workers = {}
        worker_count = 0
        app_path = Path(app.app_path)
        if app_path.exists():
            try:
                config = AppConfig.from_dir(app_path)
                workers = config.workers
                worker_count = len(workers)
            except Exception:
                # If config can't be loaded, just show empty workers
                pass

        # Prepare context
        ctx = {
            "app": {
                "name": app.name,
                "state": app.run_state.name if hasattr(app.run_state, "name") else str(app.run_state),
                "port": app.port,
                "hostname": app.hostname,
                "created_at": app.created_at,
                "updated_at": app.updated_at,
                "app_path": str(app.app_path),
                "src_path": str(app.src_path),
                "data_path": str(app.data_path),
                "log_path": str(app.log_path),
                "workers": workers,
                "worker_count": worker_count,
                "env_var_count": len(app.env_vars),
            },
            "now": datetime.now(timezone.utc),
        }

    return templates(request, "dashboard/app_detail.html", ctx)


@router.get("/dashboard/apps/{app_name}/status")
def app_status(request: Request):
    """Get application status (for HTMX polling).

    Args:
        request: The HTTP request

    Returns:
        Template response with status fragment
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    app_name = request.path_params["app_name"]

    # Get application from database
    with get_session() as db_session:
        app = db_session.query(App).filter_by(name=app_name).first()

        if not app:
            # Return empty fragment if app not found
            return templates(
                request,
                "dashboard/_app_status.html",
                {"app": None, "now": datetime.now(timezone.utc)},
            )

        # Get worker count
        worker_count = 0
        app_path = Path(app.app_path)
        if app_path.exists():
            try:
                config = AppConfig.from_dir(app_path)
                worker_count = len(config.workers)
            except Exception:
                pass

        # Prepare context for status fragment
        ctx = {
            "app": {
                "state": app.run_state.name if hasattr(app.run_state, "name") else str(app.run_state),
                "port": app.port,
                "worker_count": worker_count,
            },
            "now": datetime.now(timezone.utc),
        }

    return templates(request, "dashboard/_app_status.html", ctx)


@router.get("/dashboard/apps/{app_name}/logs")
def app_logs(request: Request):
    """Display application logs page.

    Args:
        request: The HTTP request

    Returns:
        Template response with logs viewer
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    app_name = request.path_params["app_name"]

    # Get application from database
    with get_session() as db_session:
        app = db_session.query(App).filter_by(name=app_name).first()

        if not app:
            # App not found, redirect to dashboard
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get logs (last 500 lines)
        logs = app.get_logs(lines=500)

        # Prepare context
        ctx = {
            "app_name": app.name,
            "logs": logs,
            "log_count": len(logs),
            "now": datetime.now(timezone.utc),
        }

    return templates(request, "dashboard/logs.html", ctx)


@router.get("/dashboard/apps/{app_name}/logs/stream")
def app_logs_stream(request: Request):
    """Get application logs for HTMX polling.

    Args:
        request: The HTTP request

    Returns:
        Plain text response with logs
    """
    # Require authentication
    if not request.user.is_authenticated:
        return Response(content="Unauthorized", status_code=401)

    app_name = request.path_params["app_name"]

    # Get application from database
    with get_session() as db_session:
        app = db_session.query(App).filter_by(name=app_name).first()

        if not app:
            return Response(content="App not found", status_code=404)

        # Get logs (last 500 lines)
        logs = app.get_logs(lines=500)
        log_content = "\n".join(logs)

    return Response(content=log_content, media_type="text/plain")


@router.get("/dashboard/apps/{app_name}/logs/download")
def app_logs_download(request: Request):
    """Download application logs as a text file.

    Args:
        request: The HTTP request

    Returns:
        Text file download response
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    app_name = request.path_params["app_name"]

    # Get application from database
    with get_session() as db_session:
        app = db_session.query(App).filter_by(name=app_name).first()

        if not app:
            # App not found, redirect to dashboard
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get all logs (no limit)
        logs = app.get_logs(lines=10000)  # Get more lines for download
        log_content = "\n".join(logs)

        # Create filename with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{app_name}_logs_{timestamp}.txt"

        # Return as downloadable file
        return Response(
            content=log_content,
            media_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )


@router.get("/dashboard/apps/{app_name}/env")
def app_env_vars(request: Request):
    """Display application environment variables page.

    Args:
        request: The HTTP request

    Returns:
        Template response with environment variables
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    app_name = request.path_params["app_name"]

    # Get application from database
    with get_session() as db_session:
        app = db_session.query(App).filter_by(name=app_name).first()

        if not app:
            # App not found, redirect to dashboard
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get environment variables
        env_vars = []
        service_var_count = 0

        for env_var in app.env_vars:
            # Check if this is a service-generated variable
            # Service variables typically start with service name or have _URL, _HOST, etc.
            is_service = any(
                suffix in env_var.name.upper()
                for suffix in ["_URL", "_HOST", "_PORT", "_USER", "_PASSWORD", "_DATABASE"]
            )
            if is_service:
                service_var_count += 1

            env_vars.append(
                {
                    "name": env_var.name,
                    "value": env_var.value,
                    "is_service": is_service,
                    "description": None,  # Could be added to EnvVar model later
                }
            )

        # Sort by name
        env_vars.sort(key=itemgetter("name"))

        # Prepare context
        ctx = {
            "app_name": app.name,
            "env_vars": env_vars,
            "service_var_count": service_var_count,
        }

    return templates(request, "dashboard/env_vars.html", ctx)
