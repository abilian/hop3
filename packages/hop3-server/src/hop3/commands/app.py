# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for application lifecycle and information."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from base64 import b64decode
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

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

    name: ClassVar[str] = "app"


@register
@dataclass(frozen=True)
class LaunchCmd(Command):
    """Create and configure a new app from a source code repository."""

    db_session: Session
    name: ClassVar[str] = "app:launch"

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
    name: ClassVar[str] = "deploy"

    def call(self, *args, **kwargs):
        from hop3.lib.console import capture_logs

        if not args:
            return [{"t": "text", "text": "Usage: hop deploy <app_name>"}]

        app_name = args[0]

        # Get verbosity from kwargs (default: 1=normal)
        verbosity = kwargs.get("verbosity", 1)

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

        # Capture logs during deployment
        with capture_logs(verbosity=verbosity) as captured:
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

                error_msg = "\n".join(error_parts)

                # Log to server console for debugging
                print(f"[ERROR] Deployment failed for {app_name}:", file=sys.stderr)
                print(tb, file=sys.stderr)

                # Re-raise as ValueError so RPC handler returns proper JSON-RPC error
                # This ensures the CLI client receives an Error response and exits with code 1
                raise ValueError(error_msg) from e
            except Exception as e:
                tb = traceback.format_exc()
                # Log full traceback to server console for debugging
                print(f"[ERROR] Deployment failed for {app_name}:", file=sys.stderr)
                print(tb, file=sys.stderr)

                # Build user-friendly error message (no traceback)
                error_msg = f"Deployment failed: {e}"

                # Re-raise as ValueError so RPC handler returns proper JSON-RPC error
                # This ensures the CLI client receives an Error response and exits with code 1
                raise ValueError(error_msg) from e

        # Build response with logs
        logs = captured.get_logs()
        response = []

        # Add deployment logs
        for entry in logs:
            response.append({
                "t": "log",
                "msg": entry["msg"],
                "fg": entry.get("fg", ""),
                "level": entry.get("level", 0),
            })

        # Add final success message
        response.append({
            "t": "text",
            "text": f"App '{app_name}' deployed successfully.",
        })

        return response


@register
@dataclass(frozen=True)
class StatusCmd(Command):
    """Show detailed status of an application."""

    db_session: Session
    name: ClassVar[str] = "app:status"

    def call(self, *args):
        if not args:
            return [{"t": "text", "text": "Usage: hop app:status <app_name>"}]
        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        worker_count = 0
        scaling_file = app.virtualenv_path / "SCALING"
        if scaling_file.exists():
            worker_map = parse_procfile(scaling_file)
            worker_count = sum(int(v) for v in worker_map.values())

        # Build connection URL
        if app.port:
            local_url = f"http://127.0.0.1:{app.port}"
        else:
            local_url = "Not available"

        rows = [
            ["Name", app.name],
            ["Status", app.run_state.name],
            ["Workers", str(worker_count)],
            ["Local URL", local_url],
            ["Hostname", app.hostname or "Not configured"],
        ]
        return [{"t": "table", "headers": ["Property", "Value"], "rows": rows}]


@register
@dataclass(frozen=True)
class PingCmd(Command):
    """Check if an application is responding to HTTP requests.

    Usage: hop3 app:ping <app_name> [path]

    Examples:
        hop3 app:ping myapp           # Ping root path
        hop3 app:ping myapp /health   # Ping health endpoint
    """

    db_session: Session
    name: ClassVar[str] = "app:ping"

    def call(self, *args):
        if not args:
            return [{"t": "text", "text": "Usage: hop app:ping <app_name> [path]"}]

        app_name = args[0]
        path = args[1] if len(args) > 1 else "/"
        app = _get_app(self.db_session, app_name)

        if not app.port:
            return [{"t": "error", "text": f"App '{app_name}' has no port assigned"}]

        url = f"http://127.0.0.1:{app.port}{path}"
        timeout = 10  # seconds

        try:
            start_time = time.time()
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "hop3-ping/1.0")

            with urllib.request.urlopen(req, timeout=timeout) as response:
                elapsed = (time.time() - start_time) * 1000  # ms
                status = response.status
                content_type = response.headers.get("Content-Type", "unknown")
                content_length = response.headers.get("Content-Length", "unknown")

                rows = [
                    ["URL", url],
                    ["Status", f"{status} OK"],
                    ["Response Time", f"{elapsed:.0f}ms"],
                    ["Content-Type", content_type],
                    ["Content-Length", f"{content_length} bytes"],
                ]
                return [
                    {"t": "success", "text": f"App '{app_name}' is responding"},
                    {"t": "table", "headers": ["Property", "Value"], "rows": rows},
                ]

        except urllib.error.HTTPError as e:
            elapsed = (time.time() - start_time) * 1000
            return [
                {"t": "warning", "text": f"App '{app_name}' returned HTTP {e.code}"},
                {
                    "t": "table",
                    "headers": ["Property", "Value"],
                    "rows": [
                        ["URL", url],
                        ["Status", f"{e.code} {e.reason}"],
                        ["Response Time", f"{elapsed:.0f}ms"],
                    ],
                },
            ]

        except urllib.error.URLError as e:
            reason = str(e.reason)
            if "Connection refused" in reason:
                return [
                    {
                        "t": "error",
                        "text": f"App '{app_name}' is not listening on port {app.port}",
                    },
                    {
                        "t": "text",
                        "text": "The app may not be running or may have crashed.",
                    },
                ]
            return [{"t": "error", "text": f"Connection failed: {reason}"}]

        except TimeoutError:
            return [
                {"t": "error", "text": f"App '{app_name}' timed out after {timeout}s"},
                {"t": "text", "text": "The app may be overloaded or hung."},
            ]

        except Exception as e:
            return [{"t": "error", "text": f"Error pinging app: {e}"}]


@register
@dataclass(frozen=True)
class LogsCmd(Command):
    """Show application logs."""

    db_session: Session
    name: ClassVar[str] = "app:logs"

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
    name: ClassVar[str] = "app:start"

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
    name: ClassVar[str] = "app:stop"

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
    name: ClassVar[str] = "app:restart"

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
    name: ClassVar[str] = "app:destroy"
    destructive: ClassVar[bool] = True

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
