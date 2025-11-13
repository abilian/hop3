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

from hop3.core.backup import BackupManager
from hop3.orm import App
from hop3.orm.service_credential import ServiceCredential
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
                "state": app.run_state.name
                if hasattr(app.run_state, "name")
                else str(app.run_state),
                "port": app.port,
                "created_at": app.created_at.isoformat() if app.created_at else None,
            }
            for app in apps
        ]

    ctx = {"apps": app_list}
    return templates(request, "dashboard/index.html", ctx)


@router.get("/dashboard/services")
def dashboard_services(request: Request):
    """Display services page.

    Args:
        request: The HTTP request

    Returns:
        Template response with services list
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

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


@router.get("/dashboard/backups")
def dashboard_backups(request: Request):
    """Display backups page.

    Args:
        request: The HTTP request

    Returns:
        Template response with backups list
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Get all backups from database
    with get_session() as db_session:
        manager = BackupManager(db_session)
        backup_manifests = manager.list_backups(app_name=None, limit=100)

        # Convert to dict for template
        backups = []
        for manifest in backup_manifests:
            # Extract date from backup_id (YYYYMMDD_HHMMSS_random)
            backup_id_parts = manifest.backup_id.split("_")
            if len(backup_id_parts) >= 2:
                date_str = backup_id_parts[0]
                time_str = backup_id_parts[1]
                created = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}"
            else:
                created = manifest.created_at

            # Format size
            size_bytes = manifest.size_bytes
            size = size_bytes
            unit = "B"
            for u in ["B", "KB", "MB", "GB"]:
                if size_bytes < 1024:
                    size = size_bytes
                    unit = u
                    break
                size_bytes /= 1024

            services_list = [s["name"] for s in manifest.services]

            backups.append({
                "backup_id": manifest.backup_id,
                "app_name": manifest.app_name,
                "created": created,
                "size": f"{size:.1f} {unit}",
                "services_count": len(manifest.services),
                "services": ", ".join(services_list) if services_list else "None",
            })

    ctx = {"backups": backups}
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
                "state": app.run_state.name
                if hasattr(app.run_state, "name")
                else str(app.run_state),
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
                "state": app.run_state.name
                if hasattr(app.run_state, "name")
                else str(app.run_state),
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
                for suffix in [
                    "_URL",
                    "_HOST",
                    "_PORT",
                    "_USER",
                    "_PASSWORD",
                    "_DATABASE",
                ]
            )
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

        # Prepare context
        ctx = {
            "app_name": app.name,
            "env_vars": env_vars,
            "service_var_count": service_var_count,
        }

    return templates(request, "dashboard/env_vars.html", ctx)


@router.post("/dashboard/apps/{app_name}/restart")
def app_restart(request: Request):
    """Restart an application.

    Args:
        request: The HTTP request

    Returns:
        Redirect to app detail page with success message
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    app_name = request.path_params["app_name"]

    # Restart the application
    with get_session() as db_session:
        app = db_session.query(App).filter_by(name=app_name).first()

        if not app:
            # App not found, redirect to dashboard
            return RedirectResponse(url="/dashboard", status_code=302)

        try:
            app.restart()
            db_session.commit()
        except Exception as e:
            # Log error and redirect with error
            print(f"Error restarting app {app_name}: {e}")

    # Redirect back to app detail page
    return RedirectResponse(url=f"/dashboard/apps/{app_name}", status_code=303)


@router.post("/dashboard/apps/{app_name}/backup")
def app_backup(request: Request):
    """Create a backup of an application.

    Args:
        request: The HTTP request

    Returns:
        Redirect to app detail page with success message
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    app_name = request.path_params["app_name"]

    # Create backup
    with get_session() as db_session:
        app = db_session.query(App).filter_by(name=app_name).first()

        if not app:
            # App not found, redirect to dashboard
            return RedirectResponse(url="/dashboard", status_code=302)

        try:
            manager = BackupManager(db_session)
            backup_id, backup_path = manager.create_backup(app, include_services=True)
            print(f"Backup created successfully: {backup_id} at {backup_path}")
        except Exception as e:
            # Log error and redirect with error
            print(f"Error creating backup for app {app_name}: {e}")

    # Redirect back to app detail page
    return RedirectResponse(url=f"/dashboard/apps/{app_name}", status_code=303)


@router.get("/dashboard/backups/{backup_id}/info")
def backup_info(request: Request):
    """Display detailed backup information.

    Args:
        request: The HTTP request

    Returns:
        Template response with backup details
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    backup_id = request.path_params["backup_id"]

    # Get backup info
    with get_session() as db_session:
        manager = BackupManager(db_session)

        try:
            manifest = manager.get_backup_info(backup_id)
            verification = manager.verify_backup(backup_id)
            all_valid = all(verification.values())

            # Format size
            def format_size(size_bytes: int) -> str:
                for unit in ["B", "KB", "MB", "GB"]:
                    if size_bytes < 1024:
                        return f"{size_bytes:.1f} {unit}"
                    size_bytes /= 1024
                return f"{size_bytes:.1f} TB"

            # Prepare checksums with verification status
            checksums = []
            for filename, checksum in manifest.checksums.items():
                checksums.append({
                    "filename": filename,
                    "checksum": checksum,
                    "valid": verification.get(filename, False),
                })

            ctx = {
                "backup": {
                    "backup_id": manifest.backup_id,
                    "app_name": manifest.app_name,
                    "created_at": manifest.created_at,
                    "size": format_size(manifest.size_bytes),
                    "format_version": manifest.format_version,
                    "hop3_version": manifest.hop3_version,
                    "env_vars_count": manifest.env_vars_count,
                    "services": manifest.services,
                    "app_metadata": manifest.app_metadata,
                    "checksums": checksums,
                    "all_valid": all_valid,
                },
            }

            return templates(request, "dashboard/backup_info.html", ctx)

        except FileNotFoundError:
            # Backup not found, redirect to backups page
            return RedirectResponse(url="/dashboard/backups", status_code=302)
        except Exception as e:
            print(f"Error getting backup info: {e}")
            return RedirectResponse(url="/dashboard/backups", status_code=302)


@router.post("/dashboard/backups/{backup_id}/restore")
def backup_restore(request: Request):
    """Restore a backup.

    Args:
        request: The HTTP request

    Returns:
        Redirect to backups page
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    backup_id = request.path_params["backup_id"]

    # Restore backup
    with get_session() as db_session:
        manager = BackupManager(db_session)

        try:
            # Get backup info to know which app
            manifest = manager.get_backup_info(backup_id)

            # Perform restore
            manager.restore_backup(backup_id)

            print(f"Backup {backup_id} restored successfully to {manifest.app_name}")
        except Exception as e:
            print(f"Error restoring backup {backup_id}: {e}")

    # Redirect back to backups page
    return RedirectResponse(url="/dashboard/backups", status_code=303)


@router.post("/dashboard/backups/{backup_id}/delete")
def backup_delete(request: Request):
    """Delete a backup.

    Args:
        request: The HTTP request

    Returns:
        Redirect to backups page
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    backup_id = request.path_params["backup_id"]

    # Delete backup
    with get_session() as db_session:
        manager = BackupManager(db_session)

        try:
            manager.delete_backup(backup_id)
            print(f"Backup {backup_id} deleted successfully")
        except Exception as e:
            print(f"Error deleting backup {backup_id}: {e}")

    # Redirect back to backups page
    return RedirectResponse(url="/dashboard/backups", status_code=303)
