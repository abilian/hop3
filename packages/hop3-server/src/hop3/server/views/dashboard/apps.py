# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""App-related dashboard views."""

from __future__ import annotations

from datetime import datetime, timezone
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse, Response, StreamingResponse

from hop3.core.backup import BackupManager
from hop3.project.config import AppConfig
from hop3.server.lib.database import get_session
from hop3.server.singletons import router, templates

from .db_helpers import (
    get_app_or_none,
    get_app_state_dict,
    get_services_for_app,
    get_worker_count,
)
from .utils import is_service_var, require_auth

if TYPE_CHECKING:
    from starlette.requests import Request


@router.get("/dashboard/apps/new")
@require_auth
def app_create_form(request: Request):
    """Display the create app form.

    Args:
        request: The HTTP request

    Returns:
        Template response with create app form
    """
    ctx = {
        "builders": [
            {
                "id": "auto",
                "name": "Auto-detect",
                "description": "Automatically detect builder from project files",
            },
            {
                "id": "python",
                "name": "Python",
                "description": "Python applications (Django, Flask, FastAPI, etc.)",
            },
            {
                "id": "nodejs",
                "name": "Node.js",
                "description": "Node.js applications (Express, Next.js, etc.)",
            },
            {
                "id": "static",
                "name": "Static",
                "description": "Static HTML/CSS/JS sites",
            },
            {
                "id": "ruby",
                "name": "Ruby",
                "description": "Ruby applications (Rails, Sinatra, etc.)",
            },
            {"id": "go", "name": "Go", "description": "Go applications"},
        ],
    }
    return templates(request, "dashboard/app_create.html", ctx)


@router.post("/dashboard/apps/new")
@require_auth
async def app_create_submit(request: Request):
    """Handle app creation form submission.

    Args:
        request: The HTTP request with form data

    Returns:
        Redirect to app detail page or form with errors
    """
    from hop3.orm import App, EnvVar

    # Parse form data
    form = await request.form()
    app_name = form.get("app_name", "").strip()
    builder = form.get("builder", "auto").strip()
    git_url = form.get("git_url", "").strip()
    env_vars_text = form.get("env_vars", "").strip()

    # Validation errors
    errors = []

    # Validate app name
    if not app_name:
        errors.append("App name is required")
    elif not app_name.replace("-", "").replace("_", "").isalnum():
        errors.append(
            "App name can only contain letters, numbers, hyphens, and underscores"
        )
    elif len(app_name) < 3:
        errors.append("App name must be at least 3 characters")
    elif len(app_name) > 63:
        errors.append("App name must be less than 64 characters")

    # Check if app already exists
    if not errors:
        with get_session() as db_session:
            existing_app = get_app_or_none(db_session, app_name)
            if existing_app:
                errors.append(f"App '{app_name}' already exists")

    # Parse environment variables
    env_vars = {}
    if env_vars_text:
        for line in env_vars_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    # If validation failed, return to form with errors
    if errors:
        ctx = {
            "errors": errors,
            "app_name": app_name,
            "builder": builder,
            "git_url": git_url,
            "env_vars": env_vars_text,
            "builders": [
                {
                    "id": "auto",
                    "name": "Auto-detect",
                    "description": "Automatically detect builder from project files",
                },
                {
                    "id": "python",
                    "name": "Python",
                    "description": "Python applications",
                },
                {
                    "id": "nodejs",
                    "name": "Node.js",
                    "description": "Node.js applications",
                },
                {"id": "static", "name": "Static", "description": "Static sites"},
                {"id": "ruby", "name": "Ruby", "description": "Ruby applications"},
                {"id": "go", "name": "Go", "description": "Go applications"},
            ],
        }
        return templates(request, "dashboard/app_create.html", ctx)

    # Create the app
    try:
        with get_session() as db_session:
            # Create app instance
            app = App(name=app_name)
            app.create()  # Creates directory structure

            # Add environment variables
            for key, value in env_vars.items():
                env_var = EnvVar(name=key, value=value)
                app.env_vars.append(env_var)

            # Store builder preference if not auto-detect
            if builder != "auto":
                builder_var = EnvVar(name="BUILDER", value=builder)
                app.env_vars.append(builder_var)

            db_session.add(app)
            db_session.commit()

            # Redirect to app detail page
            return RedirectResponse(
                url=f"/dashboard/apps/{app_name}?created=true", status_code=303
            )

    except Exception as e:
        # If app creation fails, show error
        errors.append(f"Failed to create app: {e!s}")
        ctx = {
            "errors": errors,
            "app_name": app_name,
            "builder": builder,
            "git_url": git_url,
            "env_vars": env_vars_text,
            "builders": [
                {
                    "id": "auto",
                    "name": "Auto-detect",
                    "description": "Automatically detect builder from project files",
                },
                {
                    "id": "python",
                    "name": "Python",
                    "description": "Python applications",
                },
                {
                    "id": "nodejs",
                    "name": "Node.js",
                    "description": "Node.js applications",
                },
                {"id": "static", "name": "Static", "description": "Static sites"},
                {"id": "ruby", "name": "Ruby", "description": "Ruby applications"},
                {"id": "go", "name": "Go", "description": "Go applications"},
            ],
        }
        return templates(request, "dashboard/app_create.html", ctx)


@router.get("/dashboard/apps/{app_name}")
@require_auth
def app_detail(request: Request):
    """Display application detail page.

    Args:
        request: The HTTP request

    Returns:
        Template response with app details
    """
    app_name = request.path_params["app_name"]

    with get_session() as db_session:
        app = get_app_or_none(db_session, app_name)

        if not app:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get workers from AppConfig if app path exists
        workers = {}
        worker_count = get_worker_count(app)
        app_path = Path(app.app_path)
        if app_path.exists():
            try:
                config = AppConfig.from_dir(app_path)
                workers = config.workers
            except Exception:
                pass

        # Get attached services
        services = get_services_for_app(app)

        # Prepare context
        ctx = {
            "app": {
                "name": app.name,
                "state": get_app_state_dict(app),
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
            "services": services,
            "now": datetime.now(timezone.utc),
        }

    return templates(request, "dashboard/app_detail.html", ctx)


@router.get("/dashboard/apps/{app_name}/status")
@require_auth
def app_status(request: Request):
    """Get application status (for HTMX polling).

    Args:
        request: The HTTP request

    Returns:
        Template response with status fragment
    """
    app_name = request.path_params["app_name"]

    with get_session() as db_session:
        app = get_app_or_none(db_session, app_name)

        if not app:
            return templates(
                request,
                "dashboard/_app_status.html",
                {"app": None, "now": datetime.now(timezone.utc)},
            )

        worker_count = get_worker_count(app)

        ctx = {
            "app": {
                "state": get_app_state_dict(app),
                "port": app.port,
                "worker_count": worker_count,
            },
            "now": datetime.now(timezone.utc),
        }

    return templates(request, "dashboard/_app_status.html", ctx)


@router.get("/dashboard/apps/{app_name}/env")
@require_auth
def app_env_vars(request: Request):
    """Display application environment variables page.

    Args:
        request: The HTTP request

    Returns:
        Template response with environment variables
    """
    app_name = request.path_params["app_name"]

    with get_session() as db_session:
        app = get_app_or_none(db_session, app_name)

        if not app:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get environment variables
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
                "description": None,  # Could be added to EnvVar model later
            })

        # Sort by name
        env_vars.sort(key=itemgetter("name"))

        ctx = {
            "app_name": app.name,
            "env_vars": env_vars,
            "service_var_count": service_var_count,
        }

    return templates(request, "dashboard/env_vars.html", ctx)


@router.post("/dashboard/apps/{app_name}/restart")
@require_auth
def app_restart(request: Request):
    """Restart an application.

    Args:
        request: The HTTP request

    Returns:
        Redirect to app detail page with success message
    """
    app_name = request.path_params["app_name"]

    with get_session() as db_session:
        app = get_app_or_none(db_session, app_name)

        if not app:
            return RedirectResponse(url="/dashboard", status_code=302)

        try:
            app.restart()
            db_session.commit()
        except Exception as e:
            print(f"Error restarting app {app_name}: {e}")

    return RedirectResponse(url=f"/dashboard/apps/{app_name}", status_code=303)


@router.post("/dashboard/apps/{app_name}/backup")
@require_auth
def app_backup(request: Request):
    """Create a backup of an application.

    Args:
        request: The HTTP request

    Returns:
        Redirect to app detail page with success message
    """
    app_name = request.path_params["app_name"]

    with get_session() as db_session:
        app = get_app_or_none(db_session, app_name)

        if not app:
            return RedirectResponse(url="/dashboard", status_code=302)

        try:
            manager = BackupManager(db_session)
            backup_id, backup_path = manager.create_backup(app, include_services=True)
            print(f"Backup created successfully: {backup_id} at {backup_path}")
        except Exception as e:
            print(f"Error creating backup for app {app_name}: {e}")

    return RedirectResponse(url=f"/dashboard/apps/{app_name}", status_code=303)


@router.get("/dashboard/apps/{app_name}/logs")
@require_auth
def app_logs(request: Request):
    """Display application logs page.

    Args:
        request: The HTTP request

    Returns:
        Template response with logs viewer
    """
    app_name = request.path_params["app_name"]

    with get_session() as db_session:
        app = get_app_or_none(db_session, app_name)

        if not app:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get logs (last 500 lines)
        logs = app.get_logs(lines=500)

        ctx = {
            "app_name": app.name,
            "logs": logs,
            "log_count": len(logs),
            "now": datetime.now(timezone.utc),
        }

    return templates(request, "dashboard/logs.html", ctx)


@router.get("/dashboard/apps/{app_name}/logs/download")
@require_auth
def app_logs_download(request: Request):
    """Download application logs as a text file.

    Args:
        request: The HTTP request

    Returns:
        Text file download response
    """
    app_name = request.path_params["app_name"]

    with get_session() as db_session:
        app = get_app_or_none(db_session, app_name)

        if not app:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get all logs (no limit)
        logs = app.get_logs(lines=10000)  # Get more lines for download
        log_content = "\n".join(logs)

        # Create filename with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{app_name}_logs_{timestamp}.txt"

        return Response(
            content=log_content,
            media_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )


@router.get("/dashboard/apps/{app_name}/logs/stream")
@require_auth
async def app_logs_stream(request: Request):
    """Stream application logs via Server-Sent Events (SSE).

    Args:
        request: The HTTP request

    Returns:
        SSE stream response
    """
    app_name = request.path_params["app_name"]

    # Get application from database
    with get_session() as db_session:
        app = get_app_or_none(db_session, app_name)

        if not app:
            return Response(
                content="App not found",
                status_code=404,
                media_type="text/plain",
            )

        log_path = Path(app.log_path)

    # Generator function for SSE
    async def log_generator():
        """Generate SSE events from log file."""
        import asyncio

        try:
            # Send initial logs (last 50 lines)
            if log_path.exists():
                with open(log_path) as f:
                    lines = f.readlines()
                    initial_lines = lines[-50:] if len(lines) > 50 else lines
                    for line in initial_lines:
                        stripped_line = line.rstrip()
                        if line:
                            # Escape newlines and send as SSE event
                            escaped_line = stripped_line.replace("\n", "\\n")
                            yield f"data: {escaped_line}\n\n"

            # Track file position for tail functionality
            file_size = log_path.stat().st_size if log_path.exists() else 0

            # Stream new lines as they appear (tail -f behavior)
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                if log_path.exists():
                    current_size = log_path.stat().st_size

                    # File has new content
                    if current_size > file_size:
                        with open(log_path) as f:
                            f.seek(file_size)
                            new_lines = f.readlines()
                            for line in new_lines:
                                stripped_line = line.rstrip()
                                if line:
                                    escaped_line = stripped_line.replace("\n", "\\n")
                                    yield f"data: {escaped_line}\n\n"

                        file_size = current_size

                    # File was truncated or rotated
                    elif current_size < file_size:
                        file_size = 0

                # Wait before checking again (1 second polling)
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            # Client disconnected
            pass
        except Exception as e:
            yield f"event: error\ndata: Error streaming logs: {e}\n\n"

    return StreamingResponse(
        content=log_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
