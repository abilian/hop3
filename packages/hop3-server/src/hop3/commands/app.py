# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for application lifecycle and information."""

from __future__ import annotations

import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from base64 import b64decode
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from hop3.core.credentials import get_credential_encryptor
from hop3.deployers import do_deploy
from hop3.lib import log
from hop3.lib.archives import extract_archive_to_dir
from hop3.lib.console import capture_logs
from hop3.lib.logging import server_log
from hop3.lib.registry import register
from hop3.orm import AddonCredential, App, AppRepository, AppStateEnum, EnvVar

from ._base import Command
from ._errors import command_context
from .apps import _get_instance_count

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
            msg = "Usage: hop launch <repo_url> <app_name>"
            raise ValueError(msg)

        repo_url, app_name = args
        app_repo = AppRepository(session=self.db_session)

        if app_repo.exists(name=app_name):
            return [{"t": "text", "text": f"Error: App '{app_name}' already exists."}]

        app = App(name=app_name)
        app.create()
        self.db_session.add(app)
        self.db_session.commit()

        try:
            with command_context("launching app", app_name=app_name, repo_url=repo_url):
                # Clone the source code into the app's src directory
                subprocess.run(
                    ["git", "clone", "--quiet", repo_url, str(app.src_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
        except ValueError:
            # Clean up if clone fails
            app.destroy()
            self.db_session.delete(app)
            self.db_session.commit()
            raise

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
        if not args:
            msg = "Usage: hop deploy <app_name>"
            raise ValueError(msg)

        app_name = args[0]

        try:
            app = _get_app(self.db_session, app_name)
            env_var_names = [ev.name for ev in app.env_vars]
            server_log.info(
                "Deploy: retrieved existing app",
                app_name=app_name,
                app_id=app.id,
                env_vars_count=len(env_var_names),
                env_vars_names=env_var_names,
            )
            if env_var_names:
                log(
                    f"App has {len(env_var_names)} env vars: {', '.join(env_var_names)}",
                    level=2,
                )
        except ValueError:
            app = App(name=app_name)
            app.create()
            self.db_session.add(app)
            self.db_session.commit()
            server_log.info("Deploy: created new app", app_name=app_name, app_id=app.id)

        # Handle --env flags: merge new env vars with existing ones
        env_vars_from_cli = kwargs.get("env_vars", {})
        if env_vars_from_cli:
            # Get existing env as dict
            existing_env = {ev.name: ev.value for ev in app.env_vars}
            # Merge with CLI env vars (CLI takes precedence)
            existing_env.update(env_vars_from_cli)
            # Update the app
            app.env_vars.clear()
            for key, value in existing_env.items():
                app.env_vars.append(EnvVar(name=key, value=value, app=app))
            self.db_session.commit()

            server_log.info(
                "Deploy: set env vars from --env",
                app_name=app_name,
                env_vars_set=list(env_vars_from_cli.keys()),
            )
            log(
                f"Set {len(env_vars_from_cli)} env var(s) from --env: {', '.join(env_vars_from_cli.keys())}"
            )

        archives_bytes = b64decode(kwargs["repository"])
        extract_archive_to_dir(archives_bytes, app.src_path)

        # Capture logs during deployment (uses global verbosity context)
        with capture_logs() as captured:
            # Use command_context for consistent error handling:
            # - Logs full traceback to stderr for debugging
            # - Converts subprocess errors to user-friendly messages
            # - Re-raises as ValueError for JSON-RPC error response
            with command_context("deploying app", app_name=app_name):
                do_deploy(app)
                # Record deployment timestamp and commit state changes
                app.last_deployed_at = datetime.now(UTC)
                self.db_session.commit()

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
            msg = "Usage: hop app:status <app_name>"
            raise ValueError(msg)
        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        # Sync state with reality for transitional states (STARTING/STOPPING)
        # This verifies actual process status and updates accordingly
        if app.run_state.name in {"STARTING", "STOPPING"}:
            app.sync_state()
            self.db_session.commit()

        # Check for state mismatch (DB says RUNNING but no processes found)
        db_state = app.run_state
        effective_state = db_state.name
        warning = None

        if db_state == AppStateEnum.RUNNING:
            actual_state = app.check_actual_status()
            if actual_state == AppStateEnum.STOPPED:
                effective_state = "CRASHED"
                warning = "No running processes found (DB state: RUNNING)"

        rows = [
            ["Name", app.name],
            ["Status", effective_state],
        ]

        if warning:
            rows.append(["Warning", warning])

        # Show helpful message for STARTING state
        if db_state == AppStateEnum.STARTING:
            rows.append(["Note", "App is starting up, please wait..."])

        # Only show runtime info if app is running
        if db_state == AppStateEnum.RUNNING and effective_state == "RUNNING":
            instance_count = _get_instance_count(app)
            rows.append(["Instances", str(instance_count)])

            if app.port:
                rows.append(["Local URL", f"http://127.0.0.1:{app.port}"])

        if app.hostname:
            rows.append(["Hostname", app.hostname])

        # Show error message if in FAILED state
        if db_state == AppStateEnum.FAILED and app.error_message:
            rows.append(["Error", app.error_message])

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
            msg = "Usage: hop app:ping <app_name> [path]"
            raise ValueError(msg)

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
        --since-deploy     Only show logs since the last deployment

    Examples:
        hop3 app:logs myapp              # Last 100 lines
        hop3 app:logs myapp -n 50        # Last 50 lines
        hop3 app:logs myapp --grep error # Lines containing 'error'
        hop3 app:logs myapp --since-deploy  # Logs since last deploy
    """

    db_session: Session
    name: ClassVar[str] = "app:logs"

    def call(self, *args):
        # Parse args: first positional is app_name, rest are options
        parsed = self._parse_args(args)
        app_name = parsed.get("app_name")

        if not app_name:
            msg = "Usage: hop3 app:logs <app_name> [options]"
            raise ValueError(msg)

        lines = parsed.get("lines", 100)
        grep = parsed.get("grep", "")
        since_deploy = parsed.get("since_deploy", False)

        app = _get_app(self.db_session, app_name)

        # Determine since timestamp if --since-deploy is used
        since = None
        if since_deploy:
            if app.last_deployed_at:
                since = app.last_deployed_at.isoformat()
            else:
                return [
                    {
                        "t": "warning",
                        "text": "No deployment timestamp found. Showing all logs.",
                    }
                ]

        log_lines = app.get_logs(lines=lines, since=since)

        # Apply grep filter if specified
        if grep:
            pattern = re.compile(grep, re.IGNORECASE)
            log_lines = [ln for ln in log_lines if pattern.search(ln)]

        if not log_lines:
            msg = "No log entries found"
            if since_deploy:
                msg += " since last deployment"
            return [{"t": "text", "text": f"{msg}."}]

        return [{"t": "text", "text": "\n".join(log_lines)}]

    def _parse_args(self, args: tuple) -> dict:
        """Parse CLI arguments: <app_name> [-n N] [--grep PATTERN] [--since-deploy]."""
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

            # Handle --since-deploy flag (no value)
            if arg == "--since-deploy":
                result["since_deploy"] = True
                i += 1
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

            # Handle --key value format (for options that take values)
            if arg.startswith("--") and i + 1 < len(args_list):
                key = arg[2:]
                # Check if next arg looks like a value (not another flag)
                next_arg = args_list[i + 1]
                if not next_arg.startswith("-"):
                    if key == "lines":
                        result[key] = int(next_arg)
                    else:
                        result[key] = next_arg
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
class BuildLogsCmd(Command):
    """Show build logs for an application.

    Usage: hop3 app:build-logs <app_name>

    Displays the most recent Docker/local build output for debugging
    deployment issues.

    Examples:
        hop3 app:build-logs myapp    # Show build logs for myapp
    """

    db_session: Session
    name: ClassVar[str] = "app:build-logs"

    def call(self, *args):
        if not args:
            msg = "Usage: hop3 app:build-logs <app_name>"
            raise ValueError(msg)

        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        # Look for build.log in app's log directory
        build_log_path = app.app_path / "log" / "build.log"

        if not build_log_path.exists():
            return [
                {
                    "t": "text",
                    "text": f"No build logs found for '{app_name}'.\n"
                    "Build logs are created after the first Docker deployment.",
                }
            ]

        try:
            content = build_log_path.read_text()
            return [{"t": "text", "text": content}]
        except Exception as e:
            return [{"t": "error", "text": f"Error reading build logs: {e}"}]


@register
@dataclass(frozen=True)
class StartCmd(Command):
    """Start a stopped app."""

    db_session: Session
    name: ClassVar[str] = "app:start"

    def call(self, *args):
        if not args:
            msg = "Usage: hop start <app_name>"
            raise ValueError(msg)
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

        # Capture logs during start operation (uses global verbosity context)
        with capture_logs() as captured:
            with command_context("starting app", app_name=app_name):
                app.start()
                self.db_session.commit()

        # Build response with captured logs
        response = []
        for entry in captured.get_logs():
            response.append({
                "t": "log",
                "msg": entry["msg"],
                "fg": entry.get("fg", ""),
                "level": entry.get("level", 0),
            })

        response.extend([
            {"t": "text", "text": f"App '{app_name}' is starting..."},
            {"t": "text", "text": "Use 'hop3 app:status' to check when it's running."},
        ])

        return response


@register
@dataclass(frozen=True)
class StopCmd(Command):
    """Stop a running app."""

    db_session: Session
    name: ClassVar[str] = "app:stop"

    def call(self, *args):
        if not args:
            msg = "Usage: hop stop <app_name>"
            raise ValueError(msg)

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

        # Capture logs during stop operation (uses global verbosity context)
        with capture_logs() as captured:
            with command_context("stopping app", app_name=app_name):
                app.stop()
                self.db_session.commit()

        # Build response with captured logs
        response = []
        for entry in captured.get_logs():
            response.append({
                "t": "log",
                "msg": entry["msg"],
                "fg": entry.get("fg", ""),
                "level": entry.get("level", 0),
            })

        response.extend([
            {"t": "text", "text": f"App '{app_name}' is stopping..."},
            {"t": "text", "text": "Use 'hop3 app:status' to check when it's stopped."},
        ])

        return response


@register
@dataclass(frozen=True)
class RestartCmd(Command):
    """Restart an application."""

    db_session: Session
    name: ClassVar[str] = "app:restart"

    def call(self, *args):
        if not args:
            msg = "Usage: hop restart <app_name>"
            raise ValueError(msg)
        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        # Capture logs during restart operation (uses global verbosity context)
        with capture_logs() as captured:
            with command_context("restarting app", app_name=app_name):
                app.restart()
                self.db_session.commit()

        # Build response with captured logs
        response = []
        for entry in captured.get_logs():
            response.append({
                "t": "log",
                "msg": entry["msg"],
                "fg": entry.get("fg", ""),
                "level": entry.get("level", 0),
            })

        response.extend([
            {"t": "text", "text": f"App '{app_name}' restart triggered."},
            {"t": "text", "text": "Use 'hop3 app:status' to check status."},
        ])

        return response


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

        app = _get_app(self.db_session, app_name)

        # Capture logs during destroy operation (uses global verbosity context)
        with capture_logs() as captured:
            with command_context("destroying app", app_name=app_name):
                log(f"Destroying app '{app_name}'...", level=2)

                # Stop the app first to release any file locks
                app.stop()

                # Clean up filesystem (repo, src, logs, configs etc.)
                app.destroy()

                # Remove from the database
                self.db_session.delete(app)
                self.db_session.commit()

                # Reload nginx to remove the app's routing configuration
                self._reload_nginx()

        # Build response with captured logs
        response = []
        for entry in captured.get_logs():
            response.append({
                "t": "log",
                "msg": entry["msg"],
                "fg": entry.get("fg", ""),
                "level": entry.get("level", 0),
            })

        response.append({"t": "text", "text": f"App '{app_name}' has been destroyed."})

        return response

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


@register
@dataclass(frozen=True)
class EnvCmd(Command):
    """Show environment variables with their sources.

    Displays all environment variables for an app, indicating whether each
    variable comes from a user config or was injected by an addon.

    Usage: hop3 app:env <app_name> [--show-secrets]

    Options:
        --show-secrets   Show full values for sensitive variables (default: redacted)

    Examples:
        hop3 app:env myapp             # Show env vars (secrets redacted)
        hop3 app:env myapp --show-secrets  # Show all values including secrets
    """

    db_session: Session
    name: ClassVar[str] = "app:env"

    # Patterns that indicate sensitive values
    SENSITIVE_PATTERNS: ClassVar[list[str]] = [
        "PASSWORD",
        "SECRET",
        "KEY",
        "TOKEN",
        "CREDENTIAL",
        "API_KEY",
    ]

    def call(self, *args):
        parsed = self._parse_args(args)
        app_name = parsed.get("app_name")

        if not app_name:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 app:env <app_name> [--show-secrets]\n\n"
                        "Examples:\n"
                        "  hop3 app:env myapp\n"
                        "  hop3 app:env myapp --show-secrets"
                    ),
                }
            ]

        show_secrets = parsed.get("show_secrets", False)
        app = _get_app(self.db_session, app_name)

        # Get addon-injected variable names
        addon_vars = self._get_addon_var_names(app)

        # Build output rows
        rows = []
        for env_var in sorted(app.env_vars, key=lambda x: x.name):
            source = "addon" if env_var.name in addon_vars else "config"
            value = (
                env_var.value
                if show_secrets
                else self._redact_if_sensitive(env_var.name, env_var.value)
            )
            rows.append([source, env_var.name, value])

        if not rows:
            return [
                {"t": "text", "text": f"No environment variables set for '{app_name}'."}
            ]

        return [
            {
                "t": "table",
                "headers": ["Source", "Name", "Value"],
                "rows": rows,
            }
        ]

    def _parse_args(self, args: tuple) -> dict:
        """Parse CLI arguments."""
        result = {}
        args_list = list(args)
        i = 0

        while i < len(args_list):
            arg = args_list[i]

            if arg == "--show-secrets":
                result["show_secrets"] = True
                i += 1
                continue

            # First non-option argument is app_name
            if not arg.startswith("-") and "app_name" not in result:
                result["app_name"] = arg
                i += 1
                continue

            i += 1

        return result

    def _get_addon_var_names(self, app) -> set[str]:
        """Get the names of environment variables injected by addons.

        Returns:
            Set of variable names that were injected by addons
        """
        addon_vars: set[str] = set()

        # Query addon credentials for this app
        credentials = (
            self.db_session.query(AddonCredential).filter_by(app_id=app.id).all()
        )

        encryptor = get_credential_encryptor()
        for credential in credentials:
            try:
                # Decrypt to get the connection details (which are the env var names)
                connection_details = encryptor.decrypt(credential.encrypted_data)
                addon_vars.update(connection_details.keys())
            except Exception:
                # If decryption fails, skip this credential
                pass

        return addon_vars

    def _redact_if_sensitive(self, name: str, value: str) -> str:
        """Redact sensitive values, showing only first 4 characters.

        Args:
            name: Environment variable name
            value: Environment variable value

        Returns:
            Redacted value if sensitive, original value otherwise
        """
        if any(pattern in name.upper() for pattern in self.SENSITIVE_PATTERNS):
            if len(value) > 4:
                return value[:4] + "***"
            return "***"
        return value


@register
@dataclass(frozen=True)
class DebugCmd(Command):
    """Comprehensive debug information for an application.

    Combines status, logs, environment, and runtime details into a single
    output for debugging issues.

    Usage: hop3 app:debug <app_name>

    Shows:
        - App status (DB state vs actual state)
        - Container information (for Docker apps)
        - Recent logs (last 20 lines)
        - Environment variables (redacted)
        - Generated compose file (for Docker apps)

    Examples:
        hop3 app:debug myapp
    """

    db_session: Session
    name: ClassVar[str] = "app:debug"

    # Patterns that indicate sensitive values
    SENSITIVE_PATTERNS: ClassVar[list[str]] = [
        "PASSWORD",
        "SECRET",
        "KEY",
        "TOKEN",
        "CREDENTIAL",
        "API_KEY",
    ]

    def call(self, *args):
        if not args:
            return [
                {
                    "t": "text",
                    "text": (
                        "Usage: hop3 app:debug <app_name>\n\n"
                        "Shows comprehensive debug information including:\n"
                        "  - App status and state\n"
                        "  - Container info (Docker apps)\n"
                        "  - Recent logs\n"
                        "  - Environment variables\n"
                        "  - Generated compose file"
                    ),
                }
            ]

        app_name = args[0]
        app = _get_app(self.db_session, app_name)

        sections = []

        # Section 1: App Status
        sections.extend(self._get_status_section(app))

        # Section 2: Container Info (Docker only)
        if app.runtime == "docker-compose":
            sections.extend(self._get_container_section(app))

        # Section 3: Recent Logs
        sections.extend(self._get_logs_section(app))

        # Section 4: Environment Variables
        sections.extend(self._get_env_section(app))

        # Section 5: Compose File (Docker only)
        if app.runtime == "docker-compose":
            sections.extend(self._get_compose_section(app))

        return sections

    def _get_status_section(self, app) -> list[dict[str, Any]]:
        """Get app status information."""
        actual_state = app.check_actual_status()
        db_state = app.run_state

        # Determine effective state
        effective_state = db_state.name
        state_mismatch = False
        if db_state == AppStateEnum.RUNNING and actual_state == AppStateEnum.STOPPED:
            effective_state = "CRASHED"
            state_mismatch = True

        rows = [
            ["Name", app.name],
            ["Runtime", app.runtime],
            ["DB State", db_state.name],
            ["Actual State", actual_state.name],
            ["Effective State", effective_state],
            ["Port", str(app.port) if app.port else "N/A"],
        ]

        if app.hostname:
            rows.append(["Hostname", app.hostname])

        if app.image_tag:
            rows.append(["Image Tag", app.image_tag])

        if app.last_deployed_at:
            rows.append([
                "Last Deployed",
                app.last_deployed_at.strftime("%Y-%m-%d %H:%M:%S"),
            ])

        if app.error_message:
            rows.append(["Error", app.error_message])

        result: list[dict[str, Any]] = [
            {"t": "text", "text": "=== APP STATUS ==="},
            {"t": "table", "headers": ["Property", "Value"], "rows": rows},
        ]

        if state_mismatch:
            result.append({
                "t": "warning",
                "text": "⚠ State mismatch detected! DB says RUNNING but no processes found.",
            })

        return result

    def _get_container_section(self, app) -> list[dict[str, Any]]:
        """Get Docker container information."""
        result = [{"t": "text", "text": "\n=== CONTAINER INFO ==="}]

        try:
            container_info = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    app.name,
                    "ps",
                    "--format",
                    "table {{.Name}}\t{{.Status}}\t{{.Ports}}",
                ],
                cwd=app.src_path,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if container_info.stdout.strip():
                result.append({"t": "text", "text": container_info.stdout.strip()})
            else:
                result.append({"t": "text", "text": "No containers found."})

            if container_info.stderr.strip():
                result.append({
                    "t": "text",
                    "text": f"stderr: {container_info.stderr.strip()}",
                })

        except subprocess.TimeoutExpired:
            result.append({"t": "text", "text": "Timeout getting container info"})
        except FileNotFoundError:
            result.append({"t": "text", "text": "Docker command not available"})
        except Exception as e:
            result.append({"t": "text", "text": f"Error: {e}"})

        return result

    def _get_logs_section(self, app) -> list[dict[str, Any]]:
        """Get recent logs."""
        result = [{"t": "text", "text": "\n=== RECENT LOGS (last 20 lines) ==="}]

        try:
            logs = app.get_logs(lines=20)
            if logs:
                result.append({"t": "text", "text": "\n".join(logs[-20:])})
            else:
                result.append({"t": "text", "text": "No logs available."})
        except Exception as e:
            result.append({"t": "text", "text": f"Error getting logs: {e}"})

        return result

    def _get_env_section(self, app) -> list[dict[str, Any]]:
        """Get environment variables (redacted)."""
        result: list[dict[str, Any]] = [
            {"t": "text", "text": "\n=== ENVIRONMENT VARIABLES ==="}
        ]

        if not app.env_vars:
            result.append({"t": "text", "text": "No environment variables set."})
            return result

        rows = []
        for env_var in sorted(app.env_vars, key=lambda x: x.name)[:15]:  # Limit to 15
            value = self._redact(env_var.name, env_var.value)
            rows.append([env_var.name, value])

        if len(app.env_vars) > 15:
            rows.append(["...", f"({len(app.env_vars) - 15} more)"])

        result.append({"t": "table", "headers": ["Name", "Value"], "rows": rows})

        return result

    def _get_compose_section(self, app) -> list[dict[str, Any]]:
        """Get generated compose file content."""
        result = [{"t": "text", "text": "\n=== GENERATED COMPOSE FILE ==="}]

        compose_path = app.src_path / ".hop3-compose.yml"
        if compose_path.exists():
            try:
                content = compose_path.read_text()
                # Truncate if too long
                if len(content) > 2000:
                    content = content[:2000] + "\n... (truncated)"
                result.append({"t": "code", "lang": "yaml", "text": content})
            except Exception as e:
                result.append({"t": "text", "text": f"Error reading compose file: {e}"})
        else:
            # Check for user-provided compose file
            for filename in ["docker-compose.yml", "docker-compose.yaml"]:
                user_compose = app.src_path / filename
                if user_compose.exists():
                    result.append({
                        "t": "text",
                        "text": f"Using user-provided {filename}",
                    })
                    break
            else:
                result.append({"t": "text", "text": "No compose file found."})

        return result

    def _redact(self, name: str, value: str) -> str:
        """Redact sensitive values."""
        if any(pattern in name.upper() for pattern in self.SENSITIVE_PATTERNS):
            if len(value) > 4:
                return value[:4] + "***"
            return "***"
        return value
