# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for application lifecycle and information."""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from base64 import b64decode
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3.deployers import do_deploy
from hop3.lib import log
from hop3.lib.archives import extract_archive_to_dir
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

    def call(self, *args, **kwargs):
        if not args:
            return [{"t": "text", "text": "Usage: hop deploy <app_name>"}]

        app_name = args[0]

        # FIXME: Q&D solution to get the app instance
        try:
            app = _get_app(self.db_session, app_name)
        except ValueError:
            app = App(name=app_name)
            app.create()
            self.db_session.add(app)
            self.db_session.commit()

        archives_bytes = b64decode(kwargs["repository"])
        extract_archive_to_dir(archives_bytes, app.src_path)

        try:
            do_deploy(app)
            # Commit the app state changes (e.g., run_state = RUNNING)
            self.db_session.commit()

        # TODO: make the exception handling a generic mechanism (reusable by other commands)
        except subprocess.CalledProcessError as e:
            # Handle subprocess errors specially to show command output
            tb = traceback.format_exc()
            error_parts = [
                f"Deployment failed: Command exited with code {e.returncode}",
                f"Command: {e.cmd}",
            ]
            if e.stdout:
                error_parts.append(f"\nStdout:\n{e.stdout}")
            if e.stderr:
                error_parts.append(f"\nStderr:\n{e.stderr}")
            error_parts.append(f"\nFull traceback:\n{tb}")

            error_msg = "\n".join(error_parts)

            # Log to server console for debugging
            print(f"[ERROR] Deployment failed for {app_name}:", file=sys.stderr)
            print(error_msg, file=sys.stderr)

            # Re-raise as ValueError so RPC handler returns proper JSON-RPC error
            # This ensures the CLI client receives an Error response and exits with code 1
            raise ValueError(error_msg) from e
        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"Deployment failed: {e}\n\nTraceback:\n{tb}"
            # Log to server console for debugging
            print(f"[ERROR] Deployment failed for {app_name}:", file=sys.stderr)
            print(tb, file=sys.stderr)

            # Re-raise as ValueError so RPC handler returns proper JSON-RPC error
            # This ensures the CLI client receives an Error response and exits with code 1
            raise ValueError(error_msg) from e

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

        debug_msgs = []

        def debug(msg):
            log(msg, level=1)
            debug_msgs.append(msg)

        debug(f"[DESTROY] Starting destroy for '{app_name}'")

        app = _get_app(self.db_session, app_name)
        debug(f"[DESTROY] App fetched from session (session id={id(self.db_session)})")

        # Stop the app first to release any file locks
        app.stop()
        debug("[DESTROY] App stopped")

        # Clean up filesystem (repo, src, logs, configs etc.)
        app.destroy()
        debug("[DESTROY] Filesystem cleaned")

        # Remove from the database
        debug("[DESTROY] Calling db_session.delete()")
        self.db_session.delete(app)

        debug("[DESTROY] Calling db_session.commit()")
        self.db_session.commit()
        debug("[DESTROY] Commit completed successfully")

        # Verify deletion
        app_repo = AppRepository(session=self.db_session)
        still_exists = app_repo.get_one_or_none(name=app_name)
        if still_exists:
            debug("[DESTROY] WARNING: App still exists in database after commit!")
        else:
            debug("[DESTROY] Verified: App no longer in database")

        # Reload nginx to remove the app's routing configuration
        self._reload_nginx()

        return [
            {
                "t": "text",
                "text": f"App '{app_name}' has been destroyed.\n\nDebug:\n"
                + "\n".join(debug_msgs),
            }
        ]

    # TODO: this should use a signal/event bus system instead
    def _reload_nginx(self) -> None:
        """Reload nginx to apply configuration changes after app destruction."""
        # Skip reload in test environments
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return

        # Try supervisorctl restart (for Docker/E2E environments)
        try:
            subprocess.run(
                ["sudo", "-n", "supervisorctl", "restart", "nginx"],
                check=True,
                capture_output=True,
                timeout=5,
            )
            log("nginx reloaded after app destruction", level=2)
            return
        except Exception:
            pass

        # Try systemctl reload (for systemd)
        try:
            subprocess.run(
                ["sudo", "-n", "systemctl", "reload", "nginx"],
                check=True,
                capture_output=True,
                timeout=5,
            )
            log("nginx reloaded after app destruction", level=2)
            return
        except Exception:
            pass

        # Silently continue if reload fails - nginx will pick up changes eventually
        log("nginx reload skipped (no reload method available)", level=3)
