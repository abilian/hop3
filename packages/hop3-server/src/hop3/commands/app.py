# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for application lifecycle and information."""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import threading
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
from hop3.lib.args import parse_cli_args
from hop3.lib.console import capture_logs
from hop3.lib.logging import server_log
from hop3.lib.registry import register
from hop3.lib.settings import parse_settings
from hop3.orm import (
    AddonCredentialRepository,
    App,
    AppRepository,
    AppStateEnum,
    EnvVar,
    get_session_factory,
)
from hop3.server.streaming import create_stream, stream_context

from ._base import Command
from ._errors import command_context
from ._helpers import get_app, redact_sensitive_value
from ._response import (
    build_log_response,
    code,
    error,
    logs_to_response,
    stream,
    success,
    table,
    text,
    warning,
)
from .apps import _get_instance_count

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _run_lifecycle_action(
    db_session: Session,
    app_name: str,
    action_name: str,
    action_method: str,
    final_messages: list[str],
    state_checks: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Run a lifecycle action (start/stop/restart) on an app.

    Args:
        db_session: Database session
        app_name: Name of the app
        action_name: Human-readable action (e.g., "starting app")
        action_method: Method name on App to call (e.g., "start")
        final_messages: Messages to show after action completes
        state_checks: Optional dict mapping state names to error messages.
            If current state matches, returns the messages immediately.

    Returns:
        Response list with logs and status messages
    """
    app = get_app(db_session, app_name)

    # Check current state if checks are provided
    if state_checks:
        state = app.run_state.name
        if state in state_checks:
            return [text(msg) for msg in state_checks[state]]

    # Capture logs during operation
    with capture_logs() as captured:
        with command_context(action_name, app_name=app_name):
            getattr(app, action_method)()
            db_session.commit()

    return build_log_response(captured, final_messages)


@register
@dataclass(frozen=True)
class AppCmd(Command):
    """Commands for managing app instances."""

    name: ClassVar[tuple[str, ...]] = ("app",)


@register
@dataclass(frozen=True)
class LaunchCmd(Command):
    """Create and configure a new app from a source code repository."""

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "launch")

    def call(self, *args):
        if len(args) != 2:
            msg = "Usage: hop launch <repo_url> <app_name>"
            raise ValueError(msg)

        repo_url, app_name = args
        app_repo = AppRepository(session=self.db_session)

        if app_repo.exists(name=app_name):
            return [error(f"App '{app_name}' already exists.")]

        app = App(name=app_name)
        app.create(setup_git=True)
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
            text(
                f"App '{app_name}' launched successfully from {repo_url}.\n"
                f"Run 'hop deploy {app_name}' to build and run it."
            )
        ]


@register
@dataclass(frozen=True)
class DeployCmd(Command):
    """Deploy an application from its configured repository."""

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("deploy",)

    def call(self, *args, **kwargs):
        if not args:
            msg = "Usage: hop deploy <app_name>"
            raise ValueError(msg)

        app_name = args[0]

        try:
            app = get_app(self.db_session, app_name)
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
            app.create(setup_git=True)
            self.db_session.add(app)
            self.db_session.commit()
            server_log.info("Deploy: created new app", app_name=app_name, app_id=app.id)

        archives_bytes = b64decode(kwargs["repository"])
        extract_archive_to_dir(archives_bytes, app.src_path)

        # Load ENV file from deployed source (provides defaults for HOST_NAME, etc.)
        env_file = app.src_path / "ENV"
        env_from_file = parse_settings(env_file) if env_file.exists() else {}

        # Get existing env vars from ORM
        existing_env = {ev.name: ev.value for ev in app.env_vars}

        # Merge: ENV file (base) <- existing ORM <- CLI flags (highest priority)
        merged_env = env_from_file.copy()
        merged_env.update(existing_env)

        # Handle --env flags from CLI (highest priority)
        env_vars_from_cli = kwargs.get("env_vars", {})
        if env_vars_from_cli:
            merged_env.update(env_vars_from_cli)
            server_log.info(
                "Deploy: set env vars from --env",
                app_name=app_name,
                env_vars_set=list(env_vars_from_cli.keys()),
            )
            log(
                f"Set {len(env_vars_from_cli)} env var(s) from --env: {', '.join(env_vars_from_cli.keys())}"
            )

        # Update ORM if anything changed
        if merged_env != existing_env:
            app.env_vars.clear()
            for key, value in merged_env.items():
                app.env_vars.append(EnvVar(name=key, value=value, app=app))
            self.db_session.commit()
            # Refresh to keep app attached to session for lazy loading in do_deploy()
            self.db_session.refresh(app)

            if env_from_file:
                server_log.info(
                    "Deploy: loaded env vars from ENV file",
                    app_name=app_name,
                    env_vars_from_file=list(env_from_file.keys()),
                )

        # Check if client requests streaming (real-time logs via SSE)
        streaming = kwargs.get("streaming", False)

        if streaming:
            return self._deploy_streaming(app, app_name)
        return self._deploy_sync(app, app_name)

    def _deploy_streaming(self, app: App, app_name: str) -> list[dict]:
        """Deploy with real-time log streaming via SSE.

        Returns stream_id immediately, runs deployment in background thread.
        """
        # Create stream for real-time logs
        log_stream = create_stream(app_name)

        # Capture app_id for the background thread (don't pass the session across threads)
        app_id = app.id

        def run_deployment():
            """Run deployment in background thread with its own session."""
            # Create a new session for this thread - sessions are not thread-safe
            session_factory = get_session_factory()
            with session_factory() as thread_session:
                try:
                    # Re-fetch the app in this thread's session
                    app_repo = AppRepository(session=thread_session)
                    thread_app = app_repo.get_one_or_none(id=app_id)
                    if not thread_app:
                        msg = f"App with id {app_id} not found"
                        raise ValueError(msg)

                    with stream_context(log_stream):
                        with command_context("deploying app", app_name=app_name):
                            do_deploy(thread_app, db_session=thread_session)
                            thread_app.last_deployed_at = datetime.now(UTC)
                            thread_session.commit()
                    log_stream.finish(success=True)
                except Exception as e:
                    # Ensure rollback on error
                    with contextlib.suppress(Exception):
                        thread_session.rollback()
                    log_stream.finish(success=False, error_message=str(e))

        # Start deployment in background thread
        thread = threading.Thread(target=run_deployment, daemon=True)
        thread.start()

        # Return stream_id immediately so CLI can connect to SSE endpoint
        return [stream(log_stream.stream_id)]

    def _deploy_sync(self, app: App, app_name: str) -> list[dict]:
        """Deploy synchronously, collecting logs for response."""
        # Capture logs during deployment (uses global verbosity context)
        with capture_logs() as captured:
            deploy_error = None
            try:
                # Use command_context for consistent error handling:
                # - Logs full traceback to stderr for debugging
                # - Converts subprocess errors to user-friendly messages
                # - Re-raises as ValueError for JSON-RPC error response
                with command_context("deploying app", app_name=app_name):
                    do_deploy(app, db_session=self.db_session)
                    # Record deployment timestamp and commit state changes
                    app.last_deployed_at = datetime.now(UTC)
                    self.db_session.commit()
            except Exception as e:
                # Rollback any uncommitted changes on error
                with contextlib.suppress(Exception):
                    self.db_session.rollback()
                deploy_error = str(e)

        # Build response with logs (always include logs, even on error)
        response = logs_to_response(captured.get_logs())

        if deploy_error:
            # Add error entry and raise with logs so CLI can display them
            response.append(error(deploy_error))
            logs_json = json.dumps(response)
            error_with_logs = f"LOGS:{logs_json}|||{deploy_error}"
            raise ValueError(error_with_logs)

        response.append(text(f"App '{app_name}' deployed successfully."))
        return response


@register
@dataclass(frozen=True)
class StatusCmd(Command):
    """Show detailed status of an application."""

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "status")

    def call(self, *args):
        if not args:
            msg = "Usage: hop app status <app_name>"
            raise ValueError(msg)
        app_name = args[0]
        app = get_app(self.db_session, app_name)

        # Sync state with reality for transitional states (STARTING/STOPPING)
        # This verifies actual process status and updates accordingly
        if app.run_state.name in {"STARTING", "STOPPING"}:
            app.sync_state()
            self.db_session.commit()

        # Check for state mismatch (DB says RUNNING but no processes found)
        db_state = app.run_state
        effective_state = db_state.name
        state_warning = None

        if db_state == AppStateEnum.RUNNING:
            actual_state = app.check_actual_status()
            if actual_state == AppStateEnum.STOPPED:
                effective_state = "CRASHED"
                state_warning = "No running processes found (DB state: RUNNING)"

        rows = [
            ["Name", app.name],
            ["Status", effective_state],
        ]

        if state_warning:
            rows.append(["Warning", state_warning])

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
            rows.append(["URL", f"https://{app.hostname}"])

        # Show error message if in FAILED state
        if db_state == AppStateEnum.FAILED and app.error_message:
            rows.append(["Error", app.error_message])

        return [table(["Property", "Value"], rows)]


@register
@dataclass(frozen=True)
class PingCmd(Command):
    """Check if an application is responding to HTTP requests.

    Usage: hop3 app ping <app_name> [path]

    Examples:
        hop3 app ping myapp           # Ping root path
        hop3 app ping myapp /health   # Ping health endpoint
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "ping")

    def call(self, *args):
        if not args:
            msg = "Usage: hop app ping <app_name> [path]"
            raise ValueError(msg)

        app_name = args[0]
        path = args[1] if len(args) > 1 else "/"
        app = get_app(self.db_session, app_name)

        if app.run_state.name == "STOPPED":
            return [text(f"App '{app_name}' is stopped.")]

        if not app.port:
            return [text(f"App '{app_name}' has no port assigned.")]

        url = f"http://127.0.0.1:{app.port}{path}"
        timeout = 10  # seconds
        start_time = time.time()

        try:
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
                    success(f"App '{app_name}' is responding"),
                    table(["Property", "Value"], rows),
                ]

        except urllib.error.HTTPError as e:
            elapsed = (time.time() - start_time) * 1000
            return [
                warning(f"App '{app_name}' returned HTTP {e.code}"),
                table(
                    ["Property", "Value"],
                    [
                        ["URL", url],
                        ["Status", f"{e.code} {e.reason}"],
                        ["Response Time", f"{elapsed:.0f}ms"],
                    ],
                ),
            ]

        except urllib.error.URLError as e:
            reason = str(e.reason)
            if "Connection refused" in reason:
                return [
                    error(f"App '{app_name}' is not listening on port {app.port}"),
                    text("The app may not be running or may have crashed."),
                ]
            return [error(f"Connection failed: {reason}")]

        except TimeoutError:
            return [
                error(f"App '{app_name}' timed out after {timeout}s"),
                text("The app may be overloaded or hung."),
            ]

        except Exception as e:
            return [error(f"Error pinging app: {e}")]


@register
@dataclass(frozen=True)
class LogsCmd(Command):
    """Show application logs.

    Usage: hop3 app logs <app_name> [options]

    Options:
        -n, --lines N      Number of lines to show (default: 100)
        --grep PATTERN     Filter lines matching pattern
        --since-deploy     Only show logs since the last deployment

    Examples:
        hop3 app logs myapp              # Last 100 lines
        hop3 app logs myapp -n 50        # Last 50 lines
        hop3 app logs myapp --grep error # Lines containing 'error'
        hop3 app logs myapp --since-deploy  # Logs since last deploy
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "logs")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app_name": {"positional": True},
        "lines": {"short": "-n", "type": int, "default": 100},
        "grep": {"type": str, "default": ""},
        "since_deploy": {"flag": True, "default": False},
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app_name")

        if not app_name:
            msg = "Usage: hop3 app logs <app_name> [options]"
            raise ValueError(msg)

        app = get_app(self.db_session, app_name)

        # Determine since timestamp if --since-deploy is used
        since = None
        if parsed["since_deploy"]:
            if app.last_deployed_at:
                since = app.last_deployed_at.isoformat()
            else:
                return [warning("No deployment timestamp found. Showing all logs.")]

        log_lines = app.get_logs(lines=parsed["lines"], since=since)

        # Apply grep filter if specified
        if parsed["grep"]:
            pattern = re.compile(parsed["grep"], re.IGNORECASE)
            log_lines = [ln for ln in log_lines if pattern.search(ln)]

        if not log_lines:
            msg = "No log entries found"
            if parsed["since_deploy"]:
                msg += " since last deployment"
            return [text(f"{msg}.")]

        return [text("\n".join(log_lines))]


@register
@dataclass(frozen=True)
class BuildLogsCmd(Command):
    """Show build logs for an application.

    Usage: hop3 app build-logs <app_name>

    Displays the most recent Docker/local build output for debugging
    deployment issues.

    Examples:
        hop3 app build-logs myapp    # Show build logs for myapp
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "build-logs")

    def call(self, *args):
        if not args:
            msg = "Usage: hop3 app build-logs <app_name>"
            raise ValueError(msg)

        app_name = args[0]
        app = get_app(self.db_session, app_name)

        # Look for build.log in app's log directory
        build_log_path = app.app_path / "log" / "build.log"

        if not build_log_path.exists():
            return [
                text(
                    f"No build logs found for '{app_name}'.\n"
                    "Build logs are created after the first Docker deployment."
                )
            ]

        try:
            content = build_log_path.read_text()
            return [text(content)]
        except Exception as e:
            return [error(f"Error reading build logs: {e}")]


@register
@dataclass(frozen=True)
class StartCmd(Command):
    """Start a stopped app."""

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "start")

    def call(self, *args):
        if not args:
            msg = "Usage: hop start <app_name>"
            raise ValueError(msg)
        app_name = args[0]
        return _run_lifecycle_action(
            self.db_session,
            app_name,
            action_name="starting app",
            action_method="start",
            final_messages=[
                f"App '{app_name}' is starting...",
                "Use 'hop3 app status' to check when it's running.",
            ],
            state_checks={
                "RUNNING": [f"App '{app_name}' is already running."],
                "STARTING": [
                    f"App '{app_name}' is already starting...",
                    "Use 'hop3 app status' to check progress.",
                ],
                "STOPPING": [
                    f"App '{app_name}' is currently stopping.",
                    "Wait for it to stop, then start it again.",
                ],
            },
        )


@register
@dataclass(frozen=True)
class StopCmd(Command):
    """Stop a running app."""

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "stop")

    def call(self, *args):
        if not args:
            msg = "Usage: hop stop <app_name>"
            raise ValueError(msg)
        app_name = args[0]
        return _run_lifecycle_action(
            self.db_session,
            app_name,
            action_name="stopping app",
            action_method="stop",
            final_messages=[
                f"App '{app_name}' is stopping...",
                "Use 'hop3 app status' to check when it's stopped.",
            ],
            state_checks={
                "STOPPED": [f"App '{app_name}' is already stopped."],
                "STOPPING": [
                    f"App '{app_name}' is already stopping...",
                    "Use 'hop3 app status' to check progress.",
                ],
                "STARTING": [
                    f"App '{app_name}' is currently starting.",
                    "Wait for it to start, then stop it.",
                ],
            },
        )


@register
@dataclass(frozen=True)
class RestartCmd(Command):
    """Restart an application."""

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "restart")

    def call(self, *args):
        if not args:
            msg = "Usage: hop restart <app_name>"
            raise ValueError(msg)
        app_name = args[0]
        return _run_lifecycle_action(
            self.db_session,
            app_name,
            action_name="restarting app",
            action_method="restart",
            final_messages=[
                f"App '{app_name}' restart triggered.",
                "Use 'hop3 app status' to check status.",
            ],
        )


@register
@dataclass(frozen=True)
class DestroyCmd(Command):
    """Destroy an app, removing all files and configuration.

    Usage: hop3 app destroy <app_name> [--force]

    Options:
      -y, --yes, --force   Skip confirmation prompt
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "destroy")
    aliases: ClassVar[list[tuple[str, ...]]] = [("destroy",)]
    destructive: ClassVar[bool] = True

    def call(self, *args):
        if not args:
            return [text("Usage: hop3 app destroy <app_name> [--force]")]
        app_name = args[0]

        app = get_app(self.db_session, app_name)

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

        return build_log_response(captured, [f"App '{app_name}' has been destroyed."])

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

    Usage: hop3 app env <app_name> [--show-secrets]

    Options:
        --show-secrets   Show full values for sensitive variables (default: redacted)

    Examples:
        hop3 app env myapp             # Show env vars (secrets redacted)
        hop3 app env myapp --show-secrets  # Show all values including secrets
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "env")
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app_name": {"positional": True},
        "show_secrets": {"flag": True, "default": False},
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app_name")

        if not app_name:
            return [
                text(
                    "Usage: hop3 app env <app_name> [--show-secrets]\n\n"
                    "Examples:\n"
                    "  hop3 app env myapp\n"
                    "  hop3 app env myapp --show-secrets"
                )
            ]

        show_secrets = parsed["show_secrets"]
        app = get_app(self.db_session, app_name)

        # Get addon-injected variable names
        addon_vars = self._get_addon_var_names(app)

        # Build output rows
        rows = []
        for env_var in sorted(app.env_vars, key=lambda x: x.name):
            source = "addon" if env_var.name in addon_vars else "config"
            value = (
                env_var.value
                if show_secrets
                else redact_sensitive_value(env_var.name, env_var.value)
            )
            rows.append([source, env_var.name, value])

        if not rows:
            return [text(f"No environment variables set for '{app_name}'.")]

        return [table(["Source", "Name", "Value"], rows)]

    def _get_addon_var_names(self, app) -> set[str]:
        """Get the names of environment variables injected by addons.

        Returns:
            Set of variable names that were injected by addons
        """
        addon_vars: set[str] = set()

        # Query addon credentials for this app using repository
        addon_credential_repo = AddonCredentialRepository(session=self.db_session)
        credentials = addon_credential_repo.get_by_app_id(app.id)

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


@register
@dataclass(frozen=True)
class DebugCmd(Command):
    """Comprehensive debug information for an application.

    Combines status, logs, environment, and runtime details into a single
    output for debugging issues.

    Usage: hop3 app debug <app_name>

    Shows:
        - App status (DB state vs actual state)
        - Container information (for Docker apps)
        - Recent logs (last 20 lines)
        - Environment variables (redacted)
        - Generated compose file (for Docker apps)

    Examples:
        hop3 app debug myapp
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "debug")

    def call(self, *args):
        if not args:
            return [
                text(
                    "Usage: hop3 app debug <app_name>\n\n"
                    "Shows comprehensive debug information including:\n"
                    "  - App status and state\n"
                    "  - Container info (Docker apps)\n"
                    "  - Recent logs\n"
                    "  - Environment variables\n"
                    "  - Generated compose file"
                )
            ]

        app_name = args[0]
        app = get_app(self.db_session, app_name)

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
            text("=== APP STATUS ==="),
            table(["Property", "Value"], rows),
        ]

        if state_mismatch:
            result.append(
                warning(
                    "State mismatch detected! DB says RUNNING but no processes found."
                )
            )

        return result

    def _get_container_section(self, app) -> list[dict[str, Any]]:
        """Get Docker container information."""
        result: list[dict[str, Any]] = [text("\n=== CONTAINER INFO ===")]

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
                result.append(text(container_info.stdout.strip()))
            else:
                result.append(text("No containers found."))

            if container_info.stderr.strip():
                result.append(text(f"stderr: {container_info.stderr.strip()}"))

        except subprocess.TimeoutExpired:
            result.append(text("Timeout getting container info"))
        except FileNotFoundError:
            result.append(text("Docker command not available"))
        except Exception as e:
            result.append(text(f"Error: {e}"))

        return result

    def _get_logs_section(self, app) -> list[dict[str, Any]]:
        """Get recent logs."""
        result: list[dict[str, Any]] = [text("\n=== RECENT LOGS (last 20 lines) ===")]

        try:
            logs = app.get_logs(lines=20)
            if logs:
                result.append(text("\n".join(logs[-20:])))
            else:
                result.append(text("No logs available."))
        except Exception as e:
            result.append(text(f"Error getting logs: {e}"))

        return result

    def _get_env_section(self, app) -> list[dict[str, Any]]:
        """Get environment variables (redacted)."""
        result: list[dict[str, Any]] = [text("\n=== ENVIRONMENT VARIABLES ===")]

        if not app.env_vars:
            result.append(text("No environment variables set."))
            return result

        rows = []
        for env_var in sorted(app.env_vars, key=lambda x: x.name)[:15]:  # Limit to 15
            value = redact_sensitive_value(env_var.name, env_var.value)
            rows.append([env_var.name, value])

        if len(app.env_vars) > 15:
            rows.append(["...", f"({len(app.env_vars) - 15} more)"])

        result.append(table(["Name", "Value"], rows))

        return result

    def _get_compose_section(self, app) -> list[dict[str, Any]]:
        """Get generated compose file content."""
        result: list[dict[str, Any]] = [text("\n=== GENERATED COMPOSE FILE ===")]

        compose_path = app.src_path / ".hop3-compose.yml"
        if compose_path.exists():
            try:
                content = compose_path.read_text()
                # Truncate if too long
                if len(content) > 2000:
                    content = content[:2000] + "\n... (truncated)"
                result.append(code(content, "yaml"))
            except Exception as e:
                result.append(text(f"Error reading compose file: {e}"))
        else:
            # Check for user-provided compose file
            for filename in ["docker-compose.yml", "docker-compose.yaml"]:
                user_compose = app.src_path / filename
                if user_compose.exists():
                    result.append(text(f"Using user-provided {filename}"))
                    break
            else:
                result.append(text("No compose file found."))

        return result
