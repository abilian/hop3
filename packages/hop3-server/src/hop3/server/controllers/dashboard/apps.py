# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard apps controller - app CRUD and management."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from urllib.parse import quote_plus

from litestar import Controller, get, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body, FromPath
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER

from hop3.core.backup import BackupManager
from hop3.deployers.admin_bootstrap import read_admin_credential
from hop3.lib.logging import server_log
from hop3.orm import App, AppAdminCredentialRepository, EnvVar
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
    get_display_state,
    get_worker_count,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

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
            config_error = None
            worker_count = get_worker_count(app)
            app_path = Path(app.app_path)
            if app_path.exists():
                try:
                    config_obj = AppConfig.from_dir(app_path)
                    workers = config_obj.workers
                except Exception as e:
                    # An unreadable Procfile/hop3.toml used to render as "this
                    # app has no workers", which is indistinguishable from a
                    # genuinely worker-less app. Show the parse error instead.
                    config_error = f"{type(e).__name__}: {e}"
                    server_log.warning(
                        "Could not read app config for dashboard",
                        app_name=app_name,
                        error=str(e),
                    )

            addons = get_addons_for_app(app)

            ctx = {
                "app": {
                    "name": app.name,
                    "state": get_display_state(app),
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
                    "config_error": config_error,
                },
                "addons": addons,
                # Existence only — the password itself is revealed on its own
                # page, so it never renders on a routinely-loaded (or
                # screen-shared) page. Checked without decrypting.
                "has_admin_credential": AppAdminCredentialRepository(
                    session=db_session
                ).get_by_app_id(app.id)
                is not None,
                "now": datetime.now(timezone.utc),
            }

        return Template(template_name="dashboard/app_detail.html", context=ctx)

    @get("/{app_name:str}/credentials", sync_to_thread=False)
    def app_credentials(self, app_name: FromPath[str]) -> Template | Redirect:
        """
        Reveal the app's initial admin credential (ADR 056).

        The dashboard counterpart of `hop3 app credentials`: without it a
        web-only operator who installs an app from the catalog can reach its
        login page with no way to get in, because the credential is printed into
        the deploy log exactly once and never again.
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            cred = read_admin_credential(app, db_session)
            if cred is not None:
                # Same lightweight audit as the CLI: a reveal is a secret read.
                server_log.info("admin credential revealed", app_name=app.name)

            ctx = {
                "app_name": app.name,
                "url": app.hostname and f"https://{app.hostname}/",
                "cred": cred,
                "now": datetime.now(timezone.utc),
            }

        return Template(template_name="dashboard/app_credentials.html", context=ctx)

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
                    "state": get_display_state(app),
                    "port": app.port,
                    "worker_count": worker_count,
                    "error_message": app.error_message,
                },
                "now": datetime.now(timezone.utc),
            }

        return Template(template_name="dashboard/_app_status.html", context=ctx)

    # These three run app lifecycle work — App.restart/stop shell out to docker
    # or uwsgi with multi-second timeouts, and a backup tars the app tree and
    # dumps its addons. The server runs a single worker (server/cli/serve.py),
    # so `sync_to_thread=False` would execute them *on the event loop* and
    # freeze auth, /rpc and every SSE deploy stream for the duration. They are
    # sync handlers offloaded to a thread; nothing here may become `async def`
    # without moving the blocking call off the loop first.

    @post("/{app_name:str}/restart", status_code=303, sync_to_thread=True)
    def app_restart(self, app_name: FromPath[str]) -> Redirect:
        """Restart an application."""
        return self._run_app_action(app_name, "restart", lambda app: app.restart())

    @post("/{app_name:str}/stop", status_code=303, sync_to_thread=True)
    def app_stop(self, app_name: FromPath[str]) -> Redirect:
        """Stop an application."""
        return self._run_app_action(app_name, "stop", lambda app: app.stop())

    @post("/{app_name:str}/backup", status_code=303, sync_to_thread=True)
    def app_backup(self, app_name: FromPath[str]) -> Redirect:
        """Create a backup of an application."""

        def _backup(app: App, db_session: Session) -> None:
            manager = BackupManager(
                BackupRepository(session=db_session),
                AppRepository(session=db_session),
                AddonCredentialRepository(session=db_session),
            )
            backup_id, backup_path = manager.create_backup(app, include_addons=True)
            server_log.info(
                "Backup created",
                app_name=app.name,
                backup_id=backup_id,
                path=str(backup_path),
            )

        return self._run_app_action(app_name, "backup", _backup, wants_session=True)

    def _run_app_action(
        self,
        app_name: str,
        action: str,
        do: Callable[..., object],
        *,
        wants_session: bool = False,
    ) -> Redirect:
        """
        Run one app mutation and report its real outcome to the browser.

        The failure path is the point. These handlers used to `print()` the
        exception to the server's stdout and redirect exactly as they do on
        success, so a failed action was indistinguishable from a successful one
        in the UI and invisible in structured logs — the fake success the
        project's fail-loud rule forbids. The reason now reaches both the
        operator (`?error=`) and the log.
        """
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)
            if not app:
                raise NotFoundException(detail=f"No such app: {app_name}")

            try:
                do(app, db_session) if wants_session else do(app)
                db_session.commit()
            except Exception as e:
                db_session.rollback()
                server_log.exception(
                    "Dashboard app action failed",
                    app_name=app_name,
                    action=action,
                    error=str(e),
                )
                reason = quote_plus(f"{type(e).__name__}: {e}")
                return Redirect(
                    path=(
                        f"/dashboard/apps/{app_name}"
                        f"?action={action}&success=false&error={reason}"
                    ),
                    status_code=HTTP_303_SEE_OTHER,
                )

        return Redirect(
            path=f"/dashboard/apps/{app_name}?action={action}&success=true",
            status_code=HTTP_303_SEE_OTHER,
        )
