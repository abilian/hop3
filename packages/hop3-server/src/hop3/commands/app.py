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
        from hop3.lib.logging import server_log

        if not args:
            return [{"t": "text", "text": "Usage: hop deploy <app_name>"}]

        app_name = args[0]

        # Get verbosity from kwargs (default: 1=normal)
        verbosity = kwargs.get("verbosity", 1)

        try:
            app = _get_app(self.db_session, app_name)
            server_log.info(
                "Deploy: retrieved existing app",
                app_name=app_name,
                app_id=app.id,
                env_vars_count=len(list(app.env_vars)),
            )
        except ValueError:
            app = App(name=app_name)
            app.create()
            self.db_session.add(app)
            self.db_session.commit()
            server_log.info("Deploy: created new app", app_name=app_name, app_id=app.id)

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
        from .apps import _get_instance_count

        if not args:
            return [{"t": "text", "text": "Usage: hop app:status <app_name>"}]
        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        # Sync state with reality for transitional states (STARTING/STOPPING)
        # This verifies actual process status and updates accordingly
        if app.run_state.name in {"STARTING", "STOPPING"}:
            app.sync_state()
            self.db_session.commit()

        rows = [
            ["Name", app.name],
            ["Status", app.run_state.name],
        ]

        # Only show runtime info if app is running
        if app.run_state.name == "RUNNING":
            instance_count = _get_instance_count(app)
            rows.append(["Instances", str(instance_count)])

            if app.port:
                rows.append(["Local URL", f"http://127.0.0.1:{app.port}"])

        if app.hostname:
            rows.append(["Hostname", app.hostname])

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

        if app.run_state.name == "STOPPED":
            return [{"t": "text", "text": f"App '{app_name}' is stopped."}]

        if not app.port:
            return [{"t": "text", "text": f"App '{app_name}' has no port assigned."}]

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
    """Show application logs.

    Usage: hop3 app:logs <app_name> [options]

    Options:
        -n, --lines N      Number of lines to show (default: 100)
        --grep PATTERN     Filter lines matching pattern

    Examples:
        hop3 app:logs myapp              # Last 100 lines
        hop3 app:logs myapp -n 50        # Last 50 lines
        hop3 app:logs myapp --grep error # Lines containing 'error'
    """

    db_session: Session
    name: ClassVar[str] = "app:logs"

    def call(self, *args):
        import re

        # Parse args: first positional is app_name, rest are options
        parsed = self._parse_args(args)
        app_name = parsed.get("app_name")

        if not app_name:
            return [{"t": "text", "text": "Usage: hop3 app:logs <app_name> [options]"}]

        lines = parsed.get("lines", 100)
        grep = parsed.get("grep", "")

        app = _get_app(self.db_session, app_name)
        log_lines = app.get_logs(lines=lines)

        # Apply grep filter if specified
        if grep:
            pattern = re.compile(grep, re.IGNORECASE)
            log_lines = [ln for ln in log_lines if pattern.search(ln)]

        if not log_lines:
            return [{"t": "text", "text": "No log entries found."}]

        return [{"t": "text", "text": "\n".join(log_lines)}]

    def _parse_args(self, args: tuple) -> dict:
        """Parse CLI arguments: <app_name> [-n N] [--grep PATTERN]."""
        result = {}
        args_list = list(args)
        i = 0

        while i < len(args_list):
            arg = args_list[i]

            # Handle -n shorthand
            if arg == "-n" and i + 1 < len(args_list):
                result["lines"] = int(args_list[i + 1])
                i += 2
                continue

            # Handle --key=value format
            if arg.startswith("--") and "=" in arg:
                key, value = arg[2:].split("=", 1)
                if key == "lines":
                    result[key] = int(value)
                else:
                    result[key] = value
                i += 1
                continue

            # Handle --key value format
            if arg.startswith("--") and i + 1 < len(args_list):
                key = arg[2:]
                value = args_list[i + 1]
                if key == "lines":
                    result[key] = int(value)
                else:
                    result[key] = value
                i += 2
                continue

            # First non-option argument is app_name
            if not arg.startswith("-") and "app_name" not in result:
                result["app_name"] = arg
                i += 1
                continue

            i += 1

        return result


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

        # Check current state (background service keeps this fresh)
        state = app.run_state.name
        if state == "RUNNING":
            return [{"t": "text", "text": f"App '{app_name}' is already running."}]
        if state == "STARTING":
            return [
                {"t": "text", "text": f"App '{app_name}' is already starting..."},
                {"t": "text", "text": "Use 'hop3 app:status' to check progress."},
            ]
        if state == "STOPPING":
            return [
                {"t": "text", "text": f"App '{app_name}' is currently stopping."},
                {"t": "text", "text": "Wait for it to stop, then start it again."},
            ]

        app.start()
        self.db_session.commit()

        return [
            {"t": "text", "text": f"App '{app_name}' is starting..."},
            {"t": "text", "text": "Use 'hop3 app:status' to check when it's running."},
        ]


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

        # Check current state (background service keeps this fresh)
        state = app.run_state.name
        if state == "STOPPED":
            return [{"t": "text", "text": f"App '{app_name}' is already stopped."}]
        if state == "STOPPING":
            return [
                {"t": "text", "text": f"App '{app_name}' is already stopping..."},
                {"t": "text", "text": "Use 'hop3 app:status' to check progress."},
            ]
        if state == "STARTING":
            return [
                {"t": "text", "text": f"App '{app_name}' is currently starting."},
                {"t": "text", "text": "Wait for it to start, then stop it."},
            ]

        app.stop()
        self.db_session.commit()

        return [
            {"t": "text", "text": f"App '{app_name}' is stopping..."},
            {"t": "text", "text": "Use 'hop3 app:status' to check when it's stopped."},
        ]


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

        return [
            {"t": "text", "text": f"App '{app_name}' restart triggered."},
            {"t": "text", "text": "Use 'hop3 app:status' to check status."},
        ]


@register
@dataclass(frozen=True)
class DestroyCmd(Command):
    """Destroy an app, removing all files and configuration.

    Usage: hop3 app:destroy <app_name> [--force]

    Options:
      -y, --yes, --force   Skip confirmation prompt
    """

    db_session: Session
    name: ClassVar[str] = "app:destroy"
    destructive: ClassVar[bool] = True

    def call(self, *args):
        if not args:
            return [
                {"t": "text", "text": "Usage: hop3 app:destroy <app_name> [--force]"}
            ]
        app_name = args[0]

        log(f"Destroying app '{app_name}'...", level=2)

        app = _get_app(self.db_session, app_name)

        # Stop the app first to release any file locks
        app.stop()

        # Clean up filesystem (repo, src, logs, configs etc.)
        app.destroy()

        # Remove from the database
        self.db_session.delete(app)
        self.db_session.commit()

        # Reload nginx to remove the app's routing configuration
        self._reload_nginx()

        return [{"t": "text", "text": f"App '{app_name}' has been destroyed."}]

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
