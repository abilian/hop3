# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard apps controller - app CRUD and management."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from litestar import Controller, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body, FromPath
from litestar.response import Redirect, Template

from hop3.core.backup import BackupManager
from hop3.orm import App, EnvVar
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
)
from hop3.project.config import AppConfig
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session

from .helpers import (
    get_addons_for_app,
    get_app_or_none,
    get_app_state_dict,
    get_worker_count,
)

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
        app.create(setup_git=True)

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


class AppsController(Controller):
    """Controller for app management routes."""

    path = "/dashboard/apps"
    guards = [auth_guard]  # ruff:ignore[mutable-class-default]

    @get("/new", sync_to_thread=False)
    def app_create_form(self) -> Template:
        """Display the create app form."""
        ctx = {"builders": BUILDER_OPTIONS}
        return Template(template_name="dashboard/app_create.html", context=ctx)

    @post("/new", status_code=303)
    async def app_create_submit(
        self,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template | Redirect:
        """Handle app creation form submission."""
        app_name = data.get("app_name", "").strip()
        builder = data.get("builder", "auto").strip()
        git_url = data.get("git_url", "").strip()
        env_vars_text = data.get("env_vars", "").strip()

        errors = _validate_app_name(app_name)
        env_vars = _parse_env_vars(env_vars_text)

        if errors:
            return _create_form_response(
                errors, app_name, builder, git_url, env_vars_text
            )

        try:
            return _create_app(app_name, builder, env_vars)
        except Exception as e:
            errors = [f"Failed to create app: {e!s}"]
            return _create_form_response(
                errors, app_name, builder, git_url, env_vars_text
            )

    @get("/{app_name:str}", sync_to_thread=False)
    def app_detail(self, app_name: FromPath[str]) -> Template | Redirect:
        """Display application detail page."""
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            workers = {}
            worker_count = get_worker_count(app)
            app_path = Path(app.app_path)
            if app_path.exists():
                try:
                    config_obj = AppConfig.from_dir(app_path)
                    workers = config_obj.workers
                except Exception:
                    pass

            addons = get_addons_for_app(app)

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

    @get("/{app_name:str}/status", sync_to_thread=False)
    def app_status(self, app_name: FromPath[str]) -> Template:
        """Get application status (for HTMX polling)."""
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Template(
                    template_name="dashboard/_app_status.html",
                    context={"app": None, "now": datetime.now(timezone.utc)},
                )

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

    @post("/{app_name:str}/restart", status_code=303, sync_to_thread=False)
    def app_restart(self, app_name: FromPath[str]) -> Redirect:
        """Restart an application."""
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            try:
                app.restart()
                db_session.commit()
                return Redirect(
                    path=f"/dashboard/apps/{app_name}?action=restart&success=true"
                )
            except Exception as e:
                print(f"Error restarting app {app_name}: {e}")
                return Redirect(
                    path=f"/dashboard/apps/{app_name}?action=restart&success=false"
                )

        return Redirect(path=f"/dashboard/apps/{app_name}")

    @post("/{app_name:str}/stop", status_code=303, sync_to_thread=False)
    def app_stop(self, app_name: FromPath[str]) -> Redirect:
        """Stop an application."""
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            try:
                app.stop()
                db_session.commit()
                return Redirect(
                    path=f"/dashboard/apps/{app_name}?action=stop&success=true"
                )
            except Exception as e:
                print(f"Error stopping app {app_name}: {e}")
                return Redirect(
                    path=f"/dashboard/apps/{app_name}?action=stop&success=false"
                )

        return Redirect(path=f"/dashboard/apps/{app_name}")

    @post("/{app_name:str}/backup", status_code=303, sync_to_thread=False)
    def app_backup(self, app_name: FromPath[str]) -> Redirect:
        """Create a backup of an application."""
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            try:
                # Create repositories for BackupManager
                backup_repo = BackupRepository(session=db_session)
                app_repo = AppRepository(session=db_session)
                addon_credential_repo = AddonCredentialRepository(session=db_session)

                manager = BackupManager(backup_repo, app_repo, addon_credential_repo)
                backup_id, backup_path = manager.create_backup(app, include_addons=True)
                print(f"Backup created successfully: {backup_id} at {backup_path}")
            except Exception as e:
                print(f"Error creating backup for app {app_name}: {e}")

        return Redirect(path=f"/dashboard/apps/{app_name}")
