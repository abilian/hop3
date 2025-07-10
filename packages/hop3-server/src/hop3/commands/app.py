# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for application lifecycle and information."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3.deploy import do_deploy
from hop3.lib.registry import register
from hop3.orm import App, AppRepository
from hop3.project.procfile import parse_procfile

from ._base import Command

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _get_app(db_session: Session, app_name: str) -> App:
    """Helper to retrieve an app or raise a consistent error."""
    app_repo = AppRepository(session=db_session)
    app = app_repo.get_one_or_none(name=app_name)
    if not app:
        msg = f"App '{app_name}' not found."
        raise ValueError(msg)
    return app


@register
@dataclass(frozen=True)
class AppCmd(Command):
    """Commands for managing app instances."""

    name = "app"


@register
@dataclass(frozen=True)
class LaunchCmd(Command):
    """Create and configure a new app from a source code repository."""

    db_session: Session
    name = "app:launch"

    def call(self, *args):
        if len(args) != 2:
            return [{"t": "text", "text": "Usage: hop launch <repo_url> <app_name>"}]

        repo_url, app_name = args
        app_repo = AppRepository(session=self.db_session)

        if app_repo.exists(name=app_name):
            return [{"t": "text", "text": f"Error: App '{app_name}' already exists."}]

        app = App(name=app_name)
        app.create()
        self.db_session.add(app)
        self.db_session.commit()

        try:
            # Clone the source code into the app's src directory
            subprocess.run(
                ["git", "clone", "--quiet", repo_url, str(app.src_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            # Clean up if clone fails
            app.destroy()
            self.db_session.delete(app)
            self.db_session.commit()
            return [{"t": "text", "text": f"Error cloning repository: {e.stderr}"}]

        return [
            {
                "t": "text",
                "text": f"App '{app_name}' launched successfully from {repo_url}.\n"
                f"Run 'hop deploy {app_name}' to build and run it.",
            }
        ]


@register
@dataclass(frozen=True)
class DeployCmd(Command):
    """Deploy an application from its configured repository."""

    db_session: Session
    name = "deploy"

    def call(self, *args):
        if not args:
            return [{"t": "text", "text": "Usage: hop deploy <app_name>"}]

        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        try:
            # Pull latest changes from the remote repository
            subprocess.run(
                ["git", "pull"],
                cwd=app.src_path,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            return [{"t": "text", "text": f"Error pulling git repository: {e.stderr}"}]

        try:
            do_deploy(app)
        except Exception as e:
            return [{"t": "text", "text": f"Deployment failed: {e}"}]

        return [{"t": "text", "text": f"App '{app_name}' deployed successfully."}]


@register
@dataclass(frozen=True)
class StatusCmd(Command):
    """Show detailed status of an application."""

    db_session: Session
    name = "app:status"

    def call(self, *args):
        if not args:
            return [{"t": "text", "text": "Usage: hop status <app_name>"}]
        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        worker_count = 0
        scaling_file = app.virtualenv_path / "SCALING"
        if scaling_file.exists():
            worker_map = parse_procfile(scaling_file)
            worker_count = sum(int(v) for v in worker_map.values())

        rows = [
            ["Name", app.name],
            ["Status", app.run_state.name],
            ["Workers", str(worker_count)],
            ["Hostname", app.hostname or "Not configured"],
            ["Port", str(app.port) if app.port else "Not assigned"],
        ]
        return [{"t": "table", "headers": ["Property", "Value"], "rows": rows}]


@register
@dataclass(frozen=True)
class LogsCmd(Command):
    """Show application logs."""

    db_session: Session
    name = "app:logs"

    def call(self, *args):
        if not args:
            return [{"t": "text", "text": "Usage: hop logs <app_name>"}]

        app_name = args[0]
        app = _get_app(self.db_session, app_name)
        # TODO: Implement log streaming and filtering by process type
        logs = app.get_logs()
        return [{"t": "text", "text": "\n".join(logs)}]


@register
@dataclass(frozen=True)
class StartCmd(Command):
    """Start a stopped app."""

    db_session: Session
    name = "app:start"

    def call(self, *args):
        if not args:
            return [{"t": "text", "text": "Usage: hop start <app_name>"}]
        app_name = args[0]
        app = _get_app(self.db_session, app_name)
        app.start()
        self.db_session.commit()
        return [{"t": "text", "text": f"App '{app_name}' is starting..."}]


@register
@dataclass(frozen=True)
class StopCmd(Command):
    """Stop a running app."""

    db_session: Session
    name = "app:stop"

    def call(self, *args):
        if not args:
            return [{"t": "text", "text": "Usage: hop stop <app_name>"}]

        app_name = args[0]
        app = _get_app(self.db_session, app_name)
        app.stop()
        self.db_session.commit()
        return [{"t": "text", "text": f"App '{app_name}' is stopping..."}]


@register
@dataclass(frozen=True)
class RestartCmd(Command):
    """Restart an application."""

    db_session: Session
    name = "app:restart"

    def call(self, *args):
        if not args:
            return [{"t": "text", "text": "Usage: hop restart <app_name>"}]
        app_name = args[0]
        app = _get_app(self.db_session, app_name)
        app.restart()
        self.db_session.commit()
        return [{"t": "text", "text": f"App '{app_name}' is restarting..."}]


@register
@dataclass(frozen=True)
class DestroyCmd(Command):
    """Destroy an app, removing all files and configuration."""

    db_session: Session
    name = "app:destroy"

    def call(self, *args):
        if not args:
            return [{"t": "text", "text": "Usage: hop destroy <app_name>"}]
        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        # Stop the app first to release any file locks
        app.stop()
        # Clean up filesystem (repo, src, logs, configs etc.)
        app.destroy()

        # Remove from the database
        self.db_session.delete(app)
        self.db_session.commit()

        return [{"t": "text", "text": f"App '{app_name}' has been destroyed."}]
