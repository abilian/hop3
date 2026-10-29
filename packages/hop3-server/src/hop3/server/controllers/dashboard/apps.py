# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# `@inject` resolves the handler annotations when it wraps them, so the types
# named in a handler signature are runtime imports.
# ruff:file-ignore[typing-only-first-party-import, typing-only-third-party-import]

"""Dashboard apps controller - app CRUD and management."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import anyio
from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, Request, get, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body, FromPath
from litestar.response import Redirect, Template
from sqlalchemy.orm import Session

from hop3.core.backup import BackupManager
from hop3.core.identifiers import InvalidIdentifierError, validate_app_name
from hop3.core.roles import Role
from hop3.deployers.admin_bootstrap import read_admin_credential
from hop3.lib.logging import server_log
from hop3.orm import App, AppAdminCredentialRepository, EnvVar
from hop3.orm.repositories import AppRepository
from hop3.project.config import AppConfig
from hop3.server.guards import RoleGuard
from hop3.server.streaming import get_stream

from .helpers import (
    FLASH_PARAM,
    get_addons_for_app,
    get_app_or_none,
    get_display_state,
    get_worker_count,
    read_flash,
    run_mutation,
)

if TYPE_CHECKING:
    from collections.abc import Callable

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


def _create_app(
    db_session: Session, app_name: str, builder: str, env_vars: dict[str, str]
) -> Redirect:
    """Create app and return redirect to detail page."""
    app = App(name=app_name)
    app.create(setup_git=True)

    for key, value in env_vars.items():
        app.env_vars.append(EnvVar(name=key, value=value))

    if builder != "auto":
        app.env_vars.append(EnvVar(name="BUILDER", value=builder))

    db_session.add(app)
    db_session.commit()

    return Redirect(path=f"/dashboard/apps/{app_name}?created=true", status_code=303)


class AppsController(Controller):
    """
    Controller for app management routes.

    Every handler that touches the database, the filesystem or a process runs
    that work on a worker thread (``anyio.to_thread``): the server has one
    worker (server/cli/serve.py), so blocking on the event loop would freeze
    auth, /rpc and every SSE deploy stream for the duration. The handlers are
    ``async`` because Dishka's ``@inject`` only wraps coroutines; the request's
    session is handed to the thread, which commits its own writes before the
    response leaves.
    """

    path = "/dashboard/apps"
    guards = [RoleGuard(Role.VIEWER)]  # ruff:ignore[mutable-class-default]

    @get("/new", sync_to_thread=False, guards=[RoleGuard(Role.DEPLOYER)])
    def app_create_form(self) -> Template:
        """Display the create app form."""
        ctx = {"builders": BUILDER_OPTIONS}
        return Template(template_name="dashboard/app_create.html", context=ctx)

    @post("/new", status_code=303, guards=[RoleGuard(Role.DEPLOYER)])
    @inject
    async def app_create_submit(
        self,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
        db_session: FromDishka[Session],
    ) -> Template | Redirect:
        """Handle app creation form submission."""
        return await anyio.to_thread.run_sync(self._create, data, db_session)

    @staticmethod
    def _create(data: dict[str, str], db_session: Session) -> Template | Redirect:
        app_name = data.get("app_name", "").strip()
        builder = data.get("builder", "auto").strip()
        git_url = data.get("git_url", "").strip()
        env_vars_text = data.get("env_vars", "").strip()

        errors: list[str] = []
        try:
            validate_app_name(app_name)
        except InvalidIdentifierError as e:
            errors.append(str(e) if app_name else "App name is required")
        if not errors and AppRepository(session=db_session).get_by_name(app_name):
            errors.append(f"App '{app_name}' already exists")
        env_vars = _parse_env_vars(env_vars_text)

        if errors:
            return _create_form_response(
                errors, app_name, builder, git_url, env_vars_text
            )

        try:
            return _create_app(db_session, app_name, builder, env_vars)
        except Exception as e:
            db_session.rollback()
            errors = [f"Failed to create app: {e!s}"]
            return _create_form_response(
                errors, app_name, builder, git_url, env_vars_text
            )

    @get("/{app_name:str}")
    @inject
    async def app_detail(
        self, request: Request, app_name: FromPath[str], db_session: FromDishka[Session]
    ) -> Template | Redirect:
        """Display application detail page."""
        flash_token = request.query_params.get(FLASH_PARAM)
        deploy_stream_id = _deploy_stream(request.query_params.get("stream"), app_name)
        return await anyio.to_thread.run_sync(
            self._detail,
            db_session,
            app_name,
            flash_token,
            request.url.path,
            deploy_stream_id,
        )

    @staticmethod
    def _detail(
        db_session: Session,
        app_name: str,
        flash_token: str | None,
        page: str,
        deploy_stream_id: str | None,
    ) -> Template | Redirect:
        # Reading the flash reads the secret key from disk: off the loop.
        flash = read_flash(flash_token, page)
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
                "error_message": app.error_message,
            },
            "addons": get_addons_for_app(app),
            # Existence only — the password itself is revealed on its own
            # page, so it never renders on a routinely-loaded (or
            # screen-shared) page. Checked without decrypting.
            "has_admin_credential": AppAdminCredentialRepository(
                session=db_session
            ).get_by_app_id(app.id)
            is not None,
            "flash": flash,
            "deploy_stream_id": deploy_stream_id,
            "now": datetime.now(timezone.utc),
        }
        return Template(template_name="dashboard/app_detail.html", context=ctx)

    @get("/{app_name:str}/credentials", guards=[RoleGuard(Role.DEPLOYER)])
    @inject
    async def app_credentials(
        self, app_name: FromPath[str], db_session: FromDishka[Session]
    ) -> Template | Redirect:
        """
        Reveal the app's initial admin credential (ADR 056).

        The dashboard counterpart of `hop3 app credentials`: without it a
        web-only operator who installs an app from the catalog can reach its
        login page with no way to get in, because the credential is printed into
        the deploy log exactly once and never again.
        """
        return await anyio.to_thread.run_sync(self._credentials, db_session, app_name)

    @staticmethod
    def _credentials(db_session: Session, app_name: str) -> Template | Redirect:
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

    @get("/{app_name:str}/status")
    @inject
    async def app_status(
        self, app_name: FromPath[str], db_session: FromDishka[Session]
    ) -> Template:
        """
        The app's recorded state, for HTMX polling.

        A read: the state-sync service keeps ``run_state`` current. Probing and
        committing here made every open page a writer every five seconds (a
        mutation on a GET), and a 500 for an app no deployer accepts.
        """
        return await anyio.to_thread.run_sync(self._status, db_session, app_name)

    @staticmethod
    def _status(db_session: Session, app_name: str) -> Template:
        app = get_app_or_none(db_session, app_name)
        if not app:
            return Template(
                template_name="dashboard/_app_status.html",
                context={"app": None, "now": datetime.now(timezone.utc)},
            )

        ctx = {
            "app": {
                "state": get_display_state(app),
                "port": app.port,
                "worker_count": get_worker_count(app),
                "error_message": app.error_message,
            },
            "now": datetime.now(timezone.utc),
        }
        return Template(template_name="dashboard/_app_status.html", context=ctx)

    # These three run app lifecycle work — App.restart/stop shell out to docker
    # or uwsgi with multi-second timeouts, and a backup tars the app tree and
    # dumps its addons — on a worker thread, like every handler here.

    @post("/{app_name:str}/restart", status_code=303, guards=[RoleGuard(Role.DEPLOYER)])
    @inject
    async def app_restart(
        self, app_name: FromPath[str], db_session: FromDishka[Session]
    ) -> Redirect:
        """Restart an application."""
        return await anyio.to_thread.run_sync(
            _run_app_action, db_session, app_name, "restart", lambda app: app.restart()
        )

    @post("/{app_name:str}/stop", status_code=303, guards=[RoleGuard(Role.DEPLOYER)])
    @inject
    async def app_stop(
        self, app_name: FromPath[str], db_session: FromDishka[Session]
    ) -> Redirect:
        """Stop an application."""
        return await anyio.to_thread.run_sync(
            _run_app_action, db_session, app_name, "stop", lambda app: app.stop()
        )

    @post("/{app_name:str}/backup", status_code=303, guards=[RoleGuard(Role.DEPLOYER)])
    @inject
    async def app_backup(
        self,
        app_name: FromPath[str],
        db_session: FromDishka[Session],
        manager: FromDishka[BackupManager],
    ) -> Redirect:
        """Create a backup of an application."""

        def _backup(app: App) -> None:
            backup_id, backup_path = manager.create_backup(app, include_addons=True)
            server_log.info(
                "Backup created",
                app_name=app.name,
                backup_id=backup_id,
                path=str(backup_path),
            )

        return await anyio.to_thread.run_sync(
            _run_app_action, db_session, app_name, "backup", _backup
        )


#: What a successful action's banner says; the action names are ours, never
#: the query string's.
_ACTION_DONE = {
    "restart": "Application '{app}' is restarting.",
    "stop": "Application '{app}' has been stopped.",
    "backup": "Backup of '{app}' completed.",
}


def _run_app_action(
    db_session: Session, app_name: str, action: str, do: Callable[[App], object]
) -> Redirect:
    """Run one mutation of ``app_name`` and report its real outcome on its page."""
    app = get_app_or_none(db_session, app_name)
    if not app:
        raise NotFoundException(detail=f"No such app: {app_name}")

    def run() -> str:
        do(app)
        return _ACTION_DONE[action].format(app=app_name)

    return run_mutation(
        db_session,
        f"/dashboard/apps/{app_name}",
        f"{action} application '{app_name}'",
        run,
        app_name=app_name,
    )


def _deploy_stream(stream_id: str | None, app_name: str) -> str | None:
    """
    The deploy stream the install form handed over, if it is this app's.

    The id comes from the query string, so it is shown only when it names a
    known stream of this very app; anything else is ignored.
    """
    deploy = get_stream(stream_id) if stream_id else None
    if deploy is None or deploy.app_name != app_name:
        return None
    return deploy.stream_id
