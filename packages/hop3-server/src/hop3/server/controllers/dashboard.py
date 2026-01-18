# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard controller for Hop3 web interface.

This controller handles all dashboard routes including:
- Main dashboard (app list)
- App management (create, detail, restart, stop, backup)
- App logs (view, download, stream)
- App environment variables
- Addons management
- Backups management
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import anyio
from litestar import Controller, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Redirect, Response, Stream, Template

from hop3.core.backup import BackupManager
from hop3.core.plugins import get_addon
from hop3.orm import App, EnvVar
from hop3.orm.addon_credential import AddonCredential
from hop3.project.config import AppConfig
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# ============================================================================
# Helper Functions (kept as utilities, not methods)
# ============================================================================

# Builder configuration list used by app creation forms
BUILDER_OPTIONS = [
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
    {
        "id": "go",
        "name": "Go",
        "description": "Go applications",
    },
]


def get_app_or_none(db_session, app_name: str) -> App | None:
    """Get app from database by name."""
    return db_session.query(App).filter_by(name=app_name).first()


def get_worker_count(app: App) -> int:
    """Get worker count for an app."""
    app_path = Path(app.app_path)
    if not app_path.exists():
        return 0

    try:
        config_obj = AppConfig.from_dir(app_path)
        return len(config_obj.workers)
    except Exception:
        return 0


def get_app_state_dict(app: App) -> str:
    """Convert app run state to string representation."""
    if hasattr(app.run_state, "name"):
        return app.run_state.name
    return str(app.run_state)


def get_addons_for_app(app: App) -> list[dict]:
    """Get list of addons attached to an app."""
    addons = []
    for credential in app.addon_credentials:
        addons.append({
            "addon_name": credential.addon_name,
            "addon_type": credential.addon_type,
            "created_at": credential.created_at.strftime("%Y-%m-%d %H:%M")
            if credential.created_at
            else "N/A",
        })
    return addons


def format_size(size_bytes: int) -> str:
    """Format size in bytes to human-readable string."""
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_backup_datetime(backup_id: str, created_at: str) -> str:
    """Extract and format datetime from backup ID."""
    backup_id_parts = backup_id.split("_")
    if len(backup_id_parts) >= 2:
        date_str = backup_id_parts[0]
        time_str = backup_id_parts[1]
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}"
    return created_at


def is_service_var(var_name: str) -> bool:
    """Check if an environment variable is service-generated."""
    service_suffixes = [
        "_URL",
        "_HOST",
        "_PORT",
        "_USER",
        "_PASSWORD",
        "_DATABASE",
    ]
    return any(suffix in var_name.upper() for suffix in service_suffixes)


def _validate_app_name(app_name: str) -> list[str]:
    """Validate app name and return list of errors."""
    errors = []

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

    return errors


def _parse_env_vars(env_vars_text: str) -> dict[str, str]:
    """Parse environment variables from text."""
    env_vars = {}
    if env_vars_text:
        for line in env_vars_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def _create_form_response(
    errors: list[str],
    app_name: str,
    builder: str,
    git_url: str,
    env_vars_text: str,
) -> Template:
    """Create template response for app creation form with errors."""
    ctx = {
        "errors": errors,
        "app_name": app_name,
        "builder": builder,
        "git_url": git_url,
        "env_vars": env_vars_text,
        "builders": BUILDER_OPTIONS,
    }
    return Template(template_name="dashboard/app_create.html", context=ctx)


def _create_app(app_name: str, builder: str, env_vars: dict[str, str]) -> Redirect:
    """Create app and return redirect to detail page."""
    with get_session() as db_session:
        app = App(name=app_name)
        app.create()

        for key, value in env_vars.items():
            env_var = EnvVar(name=key, value=value)
            app.env_vars.append(env_var)

        if builder != "auto":
            builder_var = EnvVar(name="BUILDER", value=builder)
            app.env_vars.append(builder_var)

        db_session.add(app)
        db_session.commit()

        return Redirect(
            path=f"/dashboard/apps/{app_name}?created=true", status_code=303
        )


async def _create_log_generator(log_path: Path) -> AsyncIterator[str]:
    """Create async generator for log streaming."""

    try:
        log_path_anyio = anyio.Path(log_path)

        # Send initial logs (last 50 lines)
        async for event in _send_initial_logs(log_path_anyio):
            yield event

        # Track file position for tail functionality
        file_size = await _get_file_size(log_path_anyio)

        # Stream new lines as they appear (tail -f behavior)
        while True:
            if await log_path_anyio.exists():
                current_size = (await log_path_anyio.stat()).st_size

                if current_size > file_size:
                    async for event in _send_new_log_lines(log_path, file_size):
                        yield event
                    file_size = current_size
                elif current_size < file_size:
                    file_size = 0  # File truncated or rotated

            await asyncio.sleep(1)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        yield f"event: error\ndata: Error streaming logs: {e}\n\n"


async def _get_file_size(log_path_anyio: anyio.Path) -> int:
    """Get file size or 0 if file doesn't exist."""
    if await log_path_anyio.exists():
        return (await log_path_anyio.stat()).st_size
    return 0


async def _send_initial_logs(log_path_anyio: anyio.Path) -> AsyncIterator[str]:
    """Send initial log lines (last 50) as SSE events."""
    if not await log_path_anyio.exists():
        return

    content = await log_path_anyio.read_text()
    lines = content.splitlines(keepends=True)
    initial_lines = lines[-50:] if len(lines) > 50 else lines

    for line in initial_lines:
        if line:
            escaped_line = line.rstrip().replace("\n", "\\n")
            yield f"data: {escaped_line}\n\n"


async def _send_new_log_lines(log_path: Path, file_size: int) -> AsyncIterator[str]:
    """Read and send new log lines from file."""
    async with await anyio.open_file(log_path, "r") as f:
        await f.seek(file_size)
        new_content = await f.read()
        new_lines = new_content.splitlines(keepends=True)

        for line in new_lines:
            if line:
                escaped_line = line.rstrip().replace("\n", "\\n")
                yield f"data: {escaped_line}\n\n"


# ============================================================================
# Dashboard Controller
# ============================================================================


class DashboardController(Controller):
    """Dashboard web interface controller.

    Handles all dashboard routes for viewing and managing applications,
    addons, and backups through a web interface.

    All routes require authentication via auth_guard.
    """

    path = "/dashboard"
    guards = [auth_guard]  # noqa: RUF012 - base class defines as instance var

    # ========================================================================
    # Main Dashboard
    # ========================================================================

    @get("/", status_code=200, sync_to_thread=False)
    def dashboard_index(self) -> Template:
        """Display the main dashboard with application list.

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
                    "created_at": app.created_at.isoformat()
                    if app.created_at
                    else None,
                }
                for app in apps_list
            ]

        ctx = {"apps": app_list}
        return Template(template_name="dashboard/index.html", context=ctx)

    # ========================================================================
    # App Management
    # ========================================================================

    @get("/apps/new", sync_to_thread=False)
    def app_create_form(self) -> Template:
        """Display the create app form.

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
        return Template(template_name="dashboard/app_create.html", context=ctx)

    @post("/apps/new", status_code=303)
    async def app_create_submit(
        self,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template | Redirect:
        """Handle app creation form submission.

        Args:
            data: Form data from request

        Returns:
            Redirect to app detail page or form with errors
        """
        # Parse form data
        app_name = data.get("app_name", "").strip()
        builder = data.get("builder", "auto").strip()
        git_url = data.get("git_url", "").strip()
        env_vars_text = data.get("env_vars", "").strip()

        # Validate and check for errors
        errors = _validate_app_name(app_name)
        env_vars = _parse_env_vars(env_vars_text)

        # If validation failed, return to form with errors
        if errors:
            return _create_form_response(
                errors, app_name, builder, git_url, env_vars_text
            )

        # Create the app
        try:
            return _create_app(app_name, builder, env_vars)
        except Exception as e:
            errors = [f"Failed to create app: {e!s}"]
            return _create_form_response(
                errors, app_name, builder, git_url, env_vars_text
            )

    @get("/apps/{app_name:str}", sync_to_thread=False)
    def app_detail(self, app_name: str) -> Template | Redirect:
        """Display application detail page.

        Args:
            app_name: Application name from path

        Returns:
            Template response with app details or redirect
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            # Get workers from AppConfig if app path exists
            workers = {}
            worker_count = get_worker_count(app)
            app_path = Path(app.app_path)
            if app_path.exists():
                try:
                    config_obj = AppConfig.from_dir(app_path)
                    workers = config_obj.workers
                except Exception:
                    pass

            # Get attached addons
            addons = get_addons_for_app(app)

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
                "addons": addons,
                "now": datetime.now(timezone.utc),
            }

        return Template(template_name="dashboard/app_detail.html", context=ctx)

    @get("/apps/{app_name:str}/status", sync_to_thread=False)
    def app_status(self, app_name: str) -> Template:
        """Get application status (for HTMX polling).

        This endpoint also synchronizes transitional states (STARTING/STOPPING)
        with actual running status.

        Args:
            app_name: Application name from path

        Returns:
            Template response with status fragment
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Template(
                    template_name="dashboard/_app_status.html",
                    context={"app": None, "now": datetime.now(timezone.utc)},
                )

            # Sync transitional states (STARTING->RUNNING, STOPPING->STOPPED)
            app.sync_state()
            db_session.commit()

            worker_count = get_worker_count(app)

            ctx = {
                "app": {
                    "state": get_app_state_dict(app),
                    "port": app.port,
                    "worker_count": worker_count,
                    "error_message": app.error_message,
                },
                "now": datetime.now(timezone.utc),
            }

        return Template(template_name="dashboard/_app_status.html", context=ctx)

    @get("/apps/{app_name:str}/env", sync_to_thread=False)
    def app_env_vars(self, app_name: str) -> Template | Redirect:
        """Display application environment variables page.

        Args:
            app_name: Application name from path

        Returns:
            Template response with environment variables
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

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

        return Template(template_name="dashboard/env_vars.html", context=ctx)

    @post("/apps/{app_name:str}/restart", status_code=303, sync_to_thread=False)
    def app_restart(self, app_name: str) -> Redirect:
        """Restart an application.

        Args:
            app_name: Application name from path

        Returns:
            Redirect to app detail page
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            try:
                app.restart()
                db_session.commit()
                # Add success message via query parameter
                return Redirect(
                    path=f"/dashboard/apps/{app_name}?action=restart&success=true"
                )
            except Exception as e:
                print(f"Error restarting app {app_name}: {e}")
                return Redirect(
                    path=f"/dashboard/apps/{app_name}?action=restart&success=false"
                )

        return Redirect(path=f"/dashboard/apps/{app_name}")

    @post("/apps/{app_name:str}/stop", status_code=303, sync_to_thread=False)
    def app_stop(self, app_name: str) -> Redirect:
        """Stop an application.

        Args:
            app_name: Application name from path

        Returns:
            Redirect to app detail page
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            try:
                app.stop()
                db_session.commit()
                # Add success message via query parameter
                return Redirect(
                    path=f"/dashboard/apps/{app_name}?action=stop&success=true"
                )
            except Exception as e:
                print(f"Error stopping app {app_name}: {e}")
                return Redirect(
                    path=f"/dashboard/apps/{app_name}?action=stop&success=false"
                )

        return Redirect(path=f"/dashboard/apps/{app_name}")

    @post("/apps/{app_name:str}/backup", status_code=303, sync_to_thread=False)
    def app_backup(self, app_name: str) -> Redirect:
        """Create a backup of an application.

        Args:
            app_name: Application name from path

        Returns:
            Redirect to app detail page
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            try:
                manager = BackupManager(db_session)
                backup_id, backup_path = manager.create_backup(app, include_addons=True)
                print(f"Backup created successfully: {backup_id} at {backup_path}")
            except Exception as e:
                print(f"Error creating backup for app {app_name}: {e}")

        return Redirect(path=f"/dashboard/apps/{app_name}")

    # ========================================================================
    # App Logs
    # ========================================================================

    @get("/apps/{app_name:str}/logs", sync_to_thread=False)
    def app_logs(self, app_name: str) -> Template | Redirect:
        """Display application logs page.

        Args:
            app_name: Application name from path

        Returns:
            Template response with logs viewer
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            # Get logs (last 500 lines)
            logs = app.get_logs(lines=500)

            ctx = {
                "app_name": app.name,
                "logs": logs,
                "log_count": len(logs),
                "now": datetime.now(timezone.utc),
            }

        return Template(template_name="dashboard/logs.html", context=ctx)

    @get("/apps/{app_name:str}/logs/download", sync_to_thread=False)
    def app_logs_download(self, app_name: str) -> Response | Redirect:
        """Download application logs as a text file.

        Args:
            app_name: Application name from path

        Returns:
            Text file download response
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

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

    @get("/apps/{app_name:str}/logs/stream")
    async def app_logs_stream(self, app_name: str) -> Stream | Response:
        """Stream application logs via Server-Sent Events (SSE).

        Args:
            app_name: Application name from path

        Returns:
            SSE stream response
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Response(
                    content="App not found",
                    status_code=404,
                    media_type="text/plain",
                )

            log_path = Path(app.log_path)

        return Stream(
            content=_create_log_generator(log_path),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ========================================================================
    # Addons Management
    # ========================================================================

    @get("/addons", sync_to_thread=False)
    def dashboard_addons(self) -> Template | Redirect:
        """Display addons page.

        Args:

        Returns:
            Template response with addons list
        """
        # Get all addon credentials from database
        with get_session() as db_session:
            credentials = db_session.query(AddonCredential).join(App).all()

            # Convert to dict for template
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

    @get("/addons/{addon_name:str}", sync_to_thread=False)
    def addon_detail(self, addon_name: str) -> Template:
        """Display addon detail page.

        Args:
            addon_name: Addon name from path

        Returns:
            Template response with addon details
        """
        # Get addon credential from database
        with get_session() as db_session:
            credential = (
                db_session
                .query(AddonCredential)
                .filter(AddonCredential.addon_name == addon_name)
                .first()
            )

            if not credential:
                # Addon not found
                return Template(
                    template_name="dashboard/error.html",
                    context={
                        "error_title": "Addon Not Found",
                        "error_message": f"Addon '{addon_name}' does not exist.",
                    },
                    status_code=404,
                )

            # Get app name for the addon
            app = credential.app

            # Get addon strategy and connection details
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

    # ========================================================================
    # Backups Management
    # ========================================================================

    @get("/backups", sync_to_thread=False)
    def dashboard_backups(self) -> Template | Redirect:
        """Display backups page.

        Args:

        Returns:
            Template response with backups list
        """
        # Get all backups from database
        with get_session() as db_session:
            manager = BackupManager(db_session)
            backup_manifests = manager.list_backups(app_name=None, limit=100)

            # Convert to dict for template
            backups = []
            for manifest in backup_manifests:
                created = format_backup_datetime(
                    manifest.backup_id, manifest.created_at
                )
                addons_list = [s["name"] for s in manifest.addons]

                backups.append({
                    "backup_id": manifest.backup_id,
                    "app_name": manifest.app_name,
                    "created": created,
                    "size": format_size(manifest.size_bytes),
                    "addons_count": len(manifest.addons),
                    "addons": ", ".join(addons_list) if addons_list else "None",
                })

        ctx = {"backups": backups}
        return Template(template_name="dashboard/backups.html", context=ctx)

    @get("/backups/{backup_id:str}/info", sync_to_thread=False)
    def backup_info(self, backup_id: str) -> Template | Redirect:
        """Display detailed backup information.

        Args:
            backup_id: Backup ID from path

        Returns:
            Template response with backup details
        """
        # Get backup info
        with get_session() as db_session:
            manager = BackupManager(db_session)

            try:
                manifest = manager.get_backup_info(backup_id)
                verification = manager.verify_backup(backup_id)
                all_valid = all(verification.values())

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
                        "addons": manifest.addons,
                        "app_metadata": manifest.app_metadata,
                        "checksums": checksums,
                        "all_valid": all_valid,
                    },
                }

                return Template(template_name="dashboard/backup_info.html", context=ctx)

            except FileNotFoundError:
                return Redirect(path="/dashboard/backups")
            except Exception as e:
                print(f"Error getting backup info: {e}")
                return Redirect(path="/dashboard/backups")

    @post("/backups/{backup_id:str}/restore", status_code=303, sync_to_thread=False)
    def backup_restore(self, backup_id: str) -> Redirect:
        """Restore a backup.

        Args:
            backup_id: Backup ID from path

        Returns:
            Redirect to backups page
        """
        with get_session() as db_session:
            manager = BackupManager(db_session)

            try:
                # Get backup info to know which app
                manifest = manager.get_backup_info(backup_id)

                # Perform restore
                manager.restore_backup(backup_id)

                print(
                    f"Backup {backup_id} restored successfully to {manifest.app_name}"
                )
            except Exception as e:
                print(f"Error restoring backup {backup_id}: {e}")

        return Redirect(path="/dashboard/backups")

    @post("/backups/{backup_id:str}/delete", status_code=303, sync_to_thread=False)
    def backup_delete(self, backup_id: str) -> Redirect:
        """Delete a backup.

        Args:
            backup_id: Backup ID from path

        Returns:
            Redirect to backups page
        """
        with get_session() as db_session:
            manager = BackupManager(db_session)

            try:
                manager.delete_backup(backup_id)
                print(f"Backup {backup_id} deleted successfully")
            except Exception as e:
                print(f"Error deleting backup {backup_id}: {e}")

        return Redirect(path="/dashboard/backups")
