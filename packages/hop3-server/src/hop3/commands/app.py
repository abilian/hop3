# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for application lifecycle and information."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from base64 import b64decode
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from hop3.core.backup import BackupManager
from hop3.core.identifiers import validate_app_name
from hop3.core.plugins import get_addon
from hop3.deployers import do_deploy, stop_previous_instance
from hop3.deployers.admin_bootstrap import (
    format_admin_credential,
    read_admin_credential,
)
from hop3.deployers.fixed_ports import release_fixed_ports
from hop3.deployers.waf import teardown_waf
from hop3.lib import log
from hop3.lib.archives import extract_archive_to_dir
from hop3.lib.args import parse_cli_args, pop_app_flag, reject_extra_args
from hop3.lib.console import capture_logs
from hop3.lib.logging import server_log
from hop3.lib.registry import register
from hop3.lib.rootd import LocalRootdClient, RootdError
from hop3.lib.settings import parse_settings
from hop3.orm import (
    AddonCredentialRepository,
    App,
    AppRepository,
    AppStateEnum,
    BackupRepository,
    EnvVar,
)

from ._base import Command
from ._deploy import deploy_app_streaming
from ._errors import command_context
from ._helpers import get_app, redact_sensitive_value
from ._response import (
    build_log_response,
    code,
    error,
    logs_to_response,
    success,
    summary,
    table,
    text,
    warning,
)
from .apps import _get_instance_count

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _resolve_app(
    args: tuple[str, ...], *, allow_extra: bool = False
) -> tuple[str | None, list[str]]:
    """Resolve the target app for an app-scoped command (ADR 036 D5).

    The app is taken from the ``--app`` / ``-a`` flag only. Returns
    ``(app_name, remaining_positionals)``.

    Most app-scoped commands take NO further positionals, so by default any
    leftover token after the app flag is a typo or stray flag and is rejected
    loudly — a silently-ignored ``hop3 app restart --app x --no-such-flag`` would
    otherwise report success while doing a plain restart (audit 2026-06 C9).
    Commands that legitimately take positionals (e.g. ``app ping <path>``) pass
    ``allow_extra=True`` and validate the remainder themselves.
    """
    app_name, rest = pop_app_flag(args)
    if not allow_extra:
        reject_extra_args(rest)
    return app_name, rest


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
    with (
        capture_logs() as captured,
        command_context(action_name, app_name=app_name),
    ):
        getattr(app, action_method)()
        db_session.commit()

    response = build_log_response(captured, final_messages)
    # ADR 036 D19c: one-line state-change summary per lifecycle action.
    response.append(summary(f"{action_method} triggered on {app_name}."))
    return response


@register
@dataclass(frozen=True)
class AppCmd(Command):
    """Manage applications.

    Examples:
        hop3 app create <repo_url> --app myapp  # Create a new app
        hop3 app list                           # List all apps
        hop3 app destroy --app myapp            # Destroy an app
    """

    name: ClassVar[tuple[str, ...]] = ("app",)


@register
@dataclass(frozen=True)
class LaunchCmd(Command):
    """Create and configure a new application from a source code repository.

    Examples:
        hop3 app create <repo_url> --app myapp   # Create from a repo (then `hop3 deploy`)
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "create")
    aliases: ClassVar[list[tuple[str, ...]]] = [("app", "launch")]

    def call(self, *args):
        app_name, rest = pop_app_flag(args)
        if app_name is None or len(rest) != 1:
            msg = "Usage: hop launch <repo_url> --app <app_name>"
            raise ValueError(msg)
        repo_url = rest[0]

        validate_app_name(app_name)
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
                f"Run 'hop3 deploy --app {app_name}' to build and run it."
            )
        ]


@register
@dataclass(frozen=True)
class DeployCmd(Command):
    """Deploy an application from its configured repository.

    Examples:
        hop3 deploy                   # current app (resolved from context)
        hop3 deploy --app myapp       # explicit app
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("deploy",)

    def call(self, *args, **kwargs):
        # allow_extra: `hop3 deploy --app X <dir>` forwards the source-dir
        # positional to the server, which ignores it (the source arrives as the
        # uploaded tarball in kwargs). Deploy legitimately carries that trailing
        # positional, so it must NOT be rejected like a stray arg (C9).
        app_name, _ = _resolve_app(args, allow_extra=True)
        if not app_name:
            msg = "Usage: hop3 deploy [--app <app>]"
            raise ValueError(msg)

        validate_app_name(app_name)

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

        # Stop a still-running previous instance BEFORE replacing its source:
        # extract_archive_to_dir clears src/, and a live process holding build
        # outputs there (target/*.jar, node_modules, dist) makes the next
        # rebuild race it (truncated jar, ENOTEMPTY, ETXTBSY). No-op on a first
        # deploy. See deployers.deployer.stop_previous_instance.
        stop_previous_instance(app)

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

        Delegates to the shared ``deploy_app_streaming`` helper (also used by
        ``hop3 catalog install`` and the dashboard install form), which runs the
        deploy in a daemon thread with its own session and returns the stream id.
        """
        return [deploy_app_streaming(app_name, app.id)]

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
        response.append(summary(f"deployed {app_name}."))
        return response


def _limits_rows(app: App) -> list[list[str]]:
    """Status rows for resource [limits] (ADR 046 §3): the cap, how it is enforced
    (native / docker / unenforced), and any OOM kills. Empty when no cap is set."""
    if not app.limits_enforced:
        return []
    rows = [["Limits", f"{app.limits_detail} [{app.limits_enforced}]"]]
    oom = _oom_kill_count(app)
    if oom:
        rows.append(["OOM kills", str(oom)])
    return rows


def _oom_kill_count(app: App) -> int | None:
    """Live OOM-kill count for a native-capped app (best-effort; None if unreadable).

    Reads the live cgroup leaf via hop3-rootd. None on any rootd error (daemon
    down, no leaf) — the cap itself is shown from the DB, so a failed live read
    just omits the OOM line rather than blocking or lying about the count.
    """
    if app.limits_enforced != "native":
        return None
    from hop3.lib.rootd import (  # ruff:ignore[import-outside-top-level]
        LocalRootdClient,
        RootdError,
    )

    try:
        with LocalRootdClient() as client:
            result = client.call("cgroup.read", {"app_name": app.name})
    except RootdError:
        return None
    return result.get("oom_kill") or None


@register
@dataclass(frozen=True)
class StatusCmd(Command):
    """Show detailed status of an application.

    Examples:
        hop3 app status               # current app (resolved from context)
        hop3 app status --app myapp   # explicit app
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "status")
    aliases: ClassVar[list[tuple[str, ...]]] = [("status",)]

    def call(self, *args):
        app_name, _ = _resolve_app(args)
        if not app_name:
            msg = "Usage: hop3 app status [--app <app>]"
            raise ValueError(msg)
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

        rows.extend(_limits_rows(app))

        return [table(["Property", "Value"], rows)]


@register
@dataclass(frozen=True)
class PingCmd(Command):
    """Check if an application is responding to HTTP requests.

    Usage: hop3 app ping [--app <app>] [path]

    Examples:
        hop3 app ping                    # current app (resolved from context)
        hop3 app ping --app myapp        # explicit app, root path
        hop3 app ping --app myapp /health  # explicit app, health endpoint
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "ping")

    def call(self, *args):  # ruff:ignore[too-many-return-statements] — each return is a distinct HTTP/network outcome (stopped, no-port, success, HTTPError, connection-refused, generic URLError, timeout) with its own formatted response; flattening would just rebuild the same shape with mutable bookkeeping.
        app_name, rest = _resolve_app(args, allow_extra=True)
        if not app_name:
            msg = "Usage: hop3 app ping [--app <app>] [path]"
            raise ValueError(msg)

        path = rest[0] if rest else "/"
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


def _build_log_response(app, app_name: str) -> list[dict]:
    """Build-log output, shared by `app logs --build` and `app build-logs`."""
    build_log_path = app.app_path / "log" / "build.log"
    if not build_log_path.exists():
        return [
            text(
                f"No build logs found for '{app_name}'.\n"
                "Build logs are created after the first Docker deployment."
            )
        ]
    try:
        return [text(build_log_path.read_text())]
    except Exception as e:
        return [error(f"Error reading build logs: {e}")]


@register
@dataclass(frozen=True)
class LogsCmd(Command):
    """Show application logs.

    Usage: hop3 app logs [--app <app>] [options]

    Options:
        -n, --lines N      Number of lines to show (default: 100)
        --grep PATTERN     Filter lines matching pattern
        --since-deploy     Only show logs since the last deployment
        --build            Show build logs instead of runtime logs

    Examples:
        hop3 app logs                       # current app, last 100 lines
        hop3 app logs --app myapp -n 50     # explicit app, last 50 lines
        hop3 app logs --app myapp --grep error  # lines containing 'error'
        hop3 app logs --app myapp --since-deploy  # logs since last deploy
        hop3 app logs --app myapp --build   # build output (Docker/local build)
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "logs")
    aliases: ClassVar[list[tuple[str, ...]]] = [("logs",)]
    # Argument specification for declarative parsing
    _arg_spec: ClassVar[dict] = {
        "app": {"type": str},  # --app <name> (ADR 036 D5)
        "lines": {"short": "-n", "type": int, "default": 100},
        "grep": {"type": str, "default": ""},
        "since_deploy": {"flag": True, "default": False},
        "build": {"flag": True, "default": False},
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        app_name = parsed.get("app")

        if not app_name:
            msg = "Usage: hop3 app logs [--app <app>] [options]"
            raise ValueError(msg)

        app = get_app(self.db_session, app_name)

        if parsed["build"]:
            return _build_log_response(app, app_name)

        # Determine since timestamp if --since-deploy is used
        since = None
        if parsed["since_deploy"]:
            if app.last_deployed_at:
                since = app.last_deployed_at.isoformat()
            else:
                return [warning("No deployment timestamp found. Showing all logs.")]

        log_lines = app.get_logs(lines=parsed["lines"], since=since)

        # Apply grep filter if specified.
        # SECURITY: case-insensitive *literal substring* match, not a
        # regex compile of the user-supplied string. A pathological
        # pattern (e.g. ``(a+)+b``) would otherwise catastrophic-
        # backtrack at search time and starve the worker — DoS that
        # crosses the per-app boundary into shared CPU. Most users
        # invoke ``--grep`` for substring matching anyway; if regex
        # support is ever wanted, it should arrive with a length cap
        # and a match-time timeout (signal.alarm or threading.Timer).
        if parsed["grep"]:
            needle = parsed["grep"].casefold()
            log_lines = [ln for ln in log_lines if needle in ln.casefold()]

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

    Deprecated (ADR 036 P7): use ``app logs --build``. Kept (hidden) for
    back-compat; ``hop3 app build-logs`` still works.

    Usage: hop3 app build-logs [--app <app>]
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "build-logs")
    hidden: ClassVar[bool] = True

    def call(self, *args):
        app_name, _ = _resolve_app(args)
        if not app_name:
            msg = "Usage: hop3 app build-logs [--app <app>]"
            raise ValueError(msg)

        app = get_app(self.db_session, app_name)
        return _build_log_response(app, app_name)


@register
@dataclass(frozen=True)
class StartCmd(Command):
    """Start a stopped application.

    Examples:
        hop3 app start                # current app (resolved from context)
        hop3 app start --app myapp    # explicit app
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "start")

    def call(self, *args):
        app_name, _ = _resolve_app(args)
        if not app_name:
            msg = "Usage: hop3 app start [--app <app>]"
            raise ValueError(msg)
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
    """Stop a running application.

    Examples:
        hop3 app stop                 # current app (resolved from context)
        hop3 app stop --app myapp     # explicit app
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "stop")

    def call(self, *args):
        app_name, _ = _resolve_app(args)
        if not app_name:
            msg = "Usage: hop3 app stop [--app <app>]"
            raise ValueError(msg)
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
    """Restart an application.

    Examples:
        hop3 app restart              # current app (resolved from context)
        hop3 app restart --app myapp  # explicit app
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "restart")
    aliases: ClassVar[list[tuple[str, ...]]] = [("restart",)]

    def call(self, *args):
        app_name, _ = _resolve_app(args)
        if not app_name:
            msg = "Usage: hop3 app restart [--app <app>]"
            raise ValueError(msg)
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
    """Destroy an application, removing all files and configuration.

    Usage: hop3 app destroy [--app <app>] [--force]

    Options:
      -y, --yes, --force   Skip confirmation prompt


    Examples:
        hop3 app destroy --app myapp  # explicit app (prompts for confirmation)
        hop3 app destroy --app myapp --force  # explicit app, skip prompt
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "destroy")
    aliases: ClassVar[list[tuple[str, ...]]] = [("destroy",)]
    destructive: ClassVar[bool] = True

    def call(self, *args):
        app_name, _ = _resolve_app(args)
        if not app_name:
            return [text("Usage: hop3 app destroy [--app <app>] [--force]")]

        app = get_app(self.db_session, app_name)

        # Capture logs during destroy operation (uses global verbosity context)
        with (
            capture_logs() as captured,
            command_context("destroying app", app_name=app_name),
        ):
            log(f"Destroying app '{app_name}'...", level=2)
            cleanup_failed = False

            # Stop the app first — release file locks AND reap its processes so a
            # daemon holding a fixed port can't survive teardown. A stop that
            # can't fully reap must not block DB teardown: record it and continue
            # (app.destroy() below reaps again, state-independently).
            try:
                app.stop()
            except Exception as e:
                cleanup_failed = True
                log(
                    f"Stop during destroy was incomplete for '{app_name}': {e}",
                    level=1,
                    fg="yellow",
                )

            # Tear down attached addons (DBs, redis slots) while their
            # credentials are still in the DB. Without this, addon resources
            # leak forever and eventually exhaust (e.g. Redis has 15 dbs).
            self._destroy_addons(app)

            # Fully release the app's fixed ports (firewall + registry rows)
            # BEFORE the fallible filesystem/Docker cleanup, so a stranded claim
            # can never block a future deploy of that port.
            release_fixed_ports(app, self.db_session)

            # Stop the LeWAF proxy vassal (Emperor reaps it + its daemon) and
            # remove its rules, so no proxy process/port/config is left behind.
            teardown_waf(app)

            # Clean up filesystem (repo, src, logs, configs etc.). Downgrade a
            # failure to a warning: a busy directory or a Docker hiccup must not
            # strand the app row and its port-claim/addon rows in the DB (a far
            # worse leak than a leftover directory — which we log loudly — because
            # a stranded fixed-port claim blocks every future deploy of that
            # port). The DB delete + commit below must always run.
            try:
                app.destroy()
            except Exception as e:
                cleanup_failed = True
                log(
                    f"Filesystem/Docker cleanup for '{app_name}' was incomplete: "
                    f"{e}. Removing the app from the database anyway — inspect for "
                    f"leftovers manually.",
                    level=1,
                    fg="yellow",
                )

            # Remove from the database (cascades to any remaining child rows)
            self.db_session.delete(app)
            self.db_session.commit()

            # Reload nginx to remove the app's routing configuration
            self._reload_nginx(app_name)

        # Report accurately in the summary: if filesystem/Docker cleanup failed, the app
        # is gone from the DB (port freed) but leftovers may remain — say so,
        # rather than reporting a clean success ("teardown must be verifiable").
        if cleanup_failed:
            final_message = (
                f"App '{app_name}' removed from the database, but filesystem/Docker "
                f"cleanup was incomplete — inspect for leftovers (see logs above)."
            )
            response = build_log_response(captured, [final_message])
            response.append(summary(f"destroyed {app_name} (with cleanup warnings)."))
        else:
            response = build_log_response(
                captured, [f"App '{app_name}' has been destroyed."]
            )
            response.append(summary(f"destroyed {app_name}."))
        return response

    def _destroy_addons(self, app) -> None:
        """Destroy addons attached to this app, freeing their resources.

        Symmetric with provisioning: dropping each addon's backing store
        (postgres/mysql database and role, redis logical db) reclaims
        finite resources. Best-effort — a failed teardown must not block
        the app destroy. An addon still attached to another app is kept.
        """
        repo = AddonCredentialRepository(session=self.db_session)
        for credential in list(app.addon_credentials):
            addon_type = credential.addon_type
            addon_name = credential.addon_name

            shared_with_others = any(
                c.app_id != app.id for c in repo.list_by_addon(addon_type, addon_name)
            )
            if shared_with_others:
                log(
                    f"  Keeping addon {addon_name} ({addon_type}): "
                    "still attached to another app",
                    level=2,
                )
                continue

            try:
                get_addon(addon_type, addon_name).destroy()
                log(f"  Destroyed addon {addon_name} ({addon_type})", level=2)
            except Exception as e:
                log(
                    f"  Warning: could not destroy addon {addon_name} "
                    f"({addon_type}): {e}",
                    level=1,
                    fg="yellow",
                )
                server_log.warning(
                    "Addon teardown failed during app destroy",
                    addon_name=addon_name,
                    addon_type=addon_type,
                    error=str(e),
                )

    def _reload_nginx(self, app_name: str) -> None:
        """Reload nginx (via hop3-rootd) to drop the destroyed app's route.

        Routes through the SAME hardened path as deploy: rootd reloads and
        VERIFIES nginx actually adopted the new config (a bare ``nginx -s
        reload`` returns rc=0 even when nginx rejects it and keeps the old
        config). A failed/rejected reload is surfaced loudly — never a silent
        swallow or the old "nginx will pick up changes eventually" (it won't,
        without a successful reload), which once let a poisoned nginx config
        deadlock every subsequent deploy unnoticed.
        """
        # Skip reload in unit/integration tests (no live daemon), but not E2E.
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
            "HOP3_E2E_TEST"
        ):
            return

        try:
            with LocalRootdClient() as client:
                client.call("nginx.reload", {})
            log("nginx reloaded after app destruction", level=2)
        except RootdError as e:
            # Fail loud where the operator looks: the app row is already gone,
            # so we don't abort the destroy — but the stale route may linger
            # until a successful reload, and that must not be hidden.
            log(
                f"⚠ nginx was NOT reloaded after destroying '{app_name}': {e}. "
                "The old route may still be served; run `nginx -t`, check "
                "hop3-rootd, then reload nginx.",
                level=0,
                fg="red",
            )
            server_log.warning(
                "nginx reload failed during app destroy",
                app_name=app_name,
                error=str(e),
            )


@register
@dataclass(frozen=True)
class CredentialsCmd(Command):
    """Show an app's initial admin credential (ADR 056).

    Reveals the admin login Hop3 generated when it installed the app — the same
    block shown once at install, retrievable here so it is never lost. Full
    reveal (operator-only, audited).

    Usage: hop3 app credentials [--app <app>]
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "credentials")

    def call(self, *args):
        app_name, _ = _resolve_app(args)
        if not app_name:
            msg = "Usage: hop3 app credentials [--app <app>]"
            raise ValueError(msg)
        app = get_app(self.db_session, app_name)
        cred = read_admin_credential(app, self.db_session)
        if cred is None:
            return [
                text(
                    f"App '{app_name}' has no Hop3-managed admin credential. "
                    "It either manages its own accounts or was set up before "
                    "ADR 056."
                )
            ]
        # Lightweight audit: a credential reveal is a secret read (rootd's audit
        # covers only privileged ops, so record it here where it happens).
        server_log.info("admin credential revealed", app_name=app_name)
        host_name = app.get_runtime_env().get("HOST_NAME", "")
        return [text(format_admin_credential(app_name, host_name, cred))]


@register
@dataclass(frozen=True)
class DebugCmd(Command):
    """Comprehensive debug information for an application.

    Combines status, logs, environment, and runtime details into a single
    output for debugging issues.

    Usage: hop3 app debug [--app <app>]

    Shows:
        - App status (DB state vs actual state)
        - Container information (for Docker apps)
        - Recent logs (last 20 lines)
        - Environment variables (redacted)
        - Generated compose file (for Docker apps)

    Examples:
        hop3 app debug                # current app (resolved from context)
        hop3 app debug --app myapp    # explicit app
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "debug")

    def call(self, *args):
        app_name, _ = _resolve_app(args)
        if not app_name:
            return [
                text(
                    "Usage: hop3 app debug [--app <app>]\n\n"
                    "Shows comprehensive debug information including:\n"
                    "  - App status and state\n"
                    "  - Container info (Docker apps)\n"
                    "  - Recent logs\n"
                    "  - Environment variables\n"
                    "  - Generated compose file"
                )
            ]

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

        rows.extend(_limits_rows(app))

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


# ---- Upgrade & rollback (M3.2) ----------------------------------------------
#
# `upgrade` = a *safe* redeploy: snapshot -> rebuild + `before-run` migrations +
# health-verify -> restore the snapshot on any failure. `rollback` = restore a
# chosen backup. Both are thin transactions over BackupManager + do_deploy (which
# already builds and health-verifies, raising on failure) — no new machinery.


def _backup_manager(db_session: Session) -> BackupManager:
    """A BackupManager bound to this command's session (its repos share it)."""
    return BackupManager(
        backup_repo=BackupRepository(session=db_session),
        app_repo=AppRepository(session=db_session),
        addon_credential_repo=AddonCredentialRepository(session=db_session),
    )


@register
@dataclass(frozen=True)
class AppUpgradeCmd(Command):
    """Safely redeploy an app, rolling back automatically on failure.

    Snapshots the app (source + data + config + addons), redeploys it —
    rebuilding and running the app's `before-run` migrations — and verifies it
    comes back healthy. If the build, a migration, or the health check fails,
    the app is automatically restored to the pre-upgrade snapshot.

    Fetching a new version is not part of this command yet: deploy new code the
    normal way (git push / `hop3 deploy`); `upgrade` is the safe redeploy with a
    snapshot and automatic rollback that a plain deploy lacks.

    Usage: hop3 app upgrade [--app <app>]

    Examples:
        hop3 app upgrade --app myapp
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "upgrade")

    def call(self, *args) -> list[dict]:
        app_name, _ = _resolve_app(args)
        if not app_name:
            msg = "Usage: hop3 app upgrade [--app <app>]"
            raise ValueError(msg)
        app = get_app(self.db_session, app_name)
        if app.last_deployed_at is None:
            msg = f"App '{app_name}' has never been deployed — nothing to upgrade."
            raise ValueError(msg)

        manager = _backup_manager(self.db_session)
        error_msg = None
        with capture_logs() as captured:
            # A backup failure aborts here (fail loud): no snapshot => no safe
            # upgrade, and nothing has changed yet so there is nothing to undo.
            with command_context("backing up app before upgrade", app_name=app_name):
                backup_id, _ = manager.create_backup(app)
            try:
                do_deploy(app, db_session=self.db_session)
                app.last_deployed_at = datetime.now(UTC)
                self.db_session.commit()
            except Exception as deploy_error:
                # Transaction boundary: any deploy/migration/health failure is
                # recovered by restoring the snapshot, then reported — not hidden.
                with contextlib.suppress(Exception):
                    self.db_session.rollback()
                error_msg = self._rollback(app_name, manager, backup_id, deploy_error)

        if error_msg:
            response = logs_to_response(captured.get_logs())
            response.append(error(error_msg))
            error_with_logs = f"LOGS:{json.dumps(response)}|||{error_msg}"
            raise ValueError(error_with_logs)

        response = build_log_response(
            captured, [f"App '{app_name}' upgraded (pre-upgrade backup: {backup_id})."]
        )
        response.append(summary(f"upgraded {app_name}."))
        return response

    def _rollback(
        self,
        app_name: str,
        manager: BackupManager,
        backup_id: str,
        deploy_error: Exception,
    ) -> str:
        """Restore the pre-upgrade snapshot; return the message to fail with."""
        try:
            manager.restore_backup(backup_id)
            self.db_session.commit()
        except Exception as rollback_error:
            # Worst case: report BOTH failures + the backup id — never a fake OK.
            return (
                f"Upgrade of '{app_name}' FAILED and the automatic rollback ALSO "
                f"FAILED.\n  upgrade error: {deploy_error}\n  rollback error: "
                f"{rollback_error}\nRestore manually: "
                f"hop3 backup restore {backup_id} --app {app_name}"
            )
        return (
            f"Upgrade of '{app_name}' failed and was rolled back to the pre-upgrade "
            f"snapshot ({backup_id}): {deploy_error}"
        )


@register
@dataclass(frozen=True)
class AppRollbackCmd(Command):
    """Restore an app to a previous backup (source + data + config + addons).

    Rolls the app back to a snapshot and brings it running again. Defaults to
    the most recent backup; pass `--to <backup-id>` for a specific one
    (`hop3 backup list --app <app>` lists the ids). Overwrites live data —
    writes made since the backup are lost.

    Usage: hop3 app rollback [--app <app>] [--to <backup-id>]

    Examples:
        hop3 app rollback --app myapp
        hop3 app rollback --app myapp --to 20260707_120000_ab12cd
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("app", "rollback")
    destructive: ClassVar[bool] = True

    def call(self, *args) -> list[dict]:
        app_name, rest = _resolve_app(args, allow_extra=True)
        if not app_name:
            msg = "Usage: hop3 app rollback [--app <app>] [--to <backup-id>]"
            raise ValueError(msg)
        target = parse_cli_args(rest, {"to": {"type": str}}).get("to", "")

        get_app(self.db_session, app_name)  # existence + name validation (raises)
        manager = _backup_manager(self.db_session)
        backup_id = self._resolve_backup_id(manager, app_name, target)

        with (
            capture_logs() as captured,
            command_context("rolling back app", app_name=app_name),
        ):
            manager.restore_backup(backup_id)
            self.db_session.commit()

        response = build_log_response(
            captured, [f"App '{app_name}' rolled back to backup {backup_id}."]
        )
        response.append(summary(f"rolled back {app_name} to {backup_id}."))
        return response

    @staticmethod
    def _resolve_backup_id(manager: BackupManager, app_name: str, target: str) -> str:
        """The backup to restore: an explicit --to (verified to belong to this
        app), else the most recent for this app.

        A backup from *another* app is refused: `restore_backup` targets the
        backup's OWN manifest app, so restoring a foreign id would silently stop
        and overwrite that other app while reporting this one was rolled back.
        """
        if not target:
            recent = manager.list_backups(app_name, limit=1)
            if not recent:
                msg = (
                    f"No backup to roll back to for '{app_name}'. "
                    f"Take one with `hop3 backup create --app {app_name}`."
                )
                raise ValueError(msg)
            return recent[0].backup_id

        try:
            info = manager.get_backup_info(target)
        except FileNotFoundError as exc:
            msg = f"Backup '{target}' not found."
            raise ValueError(msg) from exc
        if info.app_name != app_name:
            msg = (
                f"Backup '{target}' belongs to app '{info.app_name}', not "
                f"'{app_name}'. Roll that app back with "
                f"`hop3 app rollback --app {info.app_name} --to {target}`."
            )
            raise ValueError(msg)
        return target
