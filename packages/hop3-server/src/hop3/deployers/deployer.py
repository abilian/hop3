# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import http.client
import os
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hop3.commands._helpers import check_hostname_conflict
from hop3.config import HopConfig
from hop3.core.identifiers import InvalidIdentifierError, validate_hostname
from hop3.core.manifest import RuntimeManifestBuilder
from hop3.core.plugins import get_builder, get_deployer
from hop3.core.protocols import DeploymentContext
from hop3.deployers.addon_provisioning import (
    provision_addons,
    reinject_attached_addons,
)
from hop3.deployers.admin_bootstrap import (
    AdminBootstrapError,
    bootstrap_admin_account,
    provision_admin_credential,
    surface_admin_credential,
)
from hop3.deployers.env_provisioning import (
    resolve_env_refs,
    set_computed_env_vars,
    set_default_env_vars,
    set_env_vars,
    set_generated_env_vars,
    set_public_url_env,
)
from hop3.deployers.fixed_ports import claim_fixed_ports, open_fixed_ports
from hop3.deployers.limits import LimitsError, resolve_limits
from hop3.deployers.native_limits import enforce_native_limits, format_limits_detail
from hop3.deployers.probe_account import (
    bootstrap_probe_account,
    provision_probe_credential,
)
from hop3.deployers.volumes import realize_volumes
from hop3.deployers.waf import configure_waf_preflight, start_waf_proxy
from hop3.lib import Abort, Diagnosis, abort_with_diagnosis, log, log_diagnosis, shell
from hop3.lib.logging import server_log
from hop3.orm.app import AppStateEnum
from hop3.plugins.proxy._policy import ALLOW_HTTP_KEY
from hop3.project.config import AppConfig

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session

    from hop3.core.artifacts import BuildArtifact
    from hop3.core.protocols import DeploymentInfo
    from hop3.orm.app import App
    from hop3.project.hop3_config import Hop3Config

__all__ = ["do_deploy"]


def do_deploy(
    app: App,
    *,
    deltas: dict[str, int] | None = None,
    db_session: Session | None = None,
) -> None:
    """
    Deploy an app; on failure, best-effort alert the operator, then re-raise.

    This is the single choke point for the deploy-failure notification event
    (ADR 054): a failed deploy emails the operator through the configured email
    backend, opt-in. The alert is best-effort and never masks the deploy
    failure — the original exception always propagates.
    """
    try:
        _do_deploy(app, deltas=deltas, db_session=db_session)
    except Exception as exc:
        _notify_deploy_failure(app, exc)
        raise


def _notify_deploy_failure(app: App, exc: BaseException) -> None:
    """Best-effort operator alert on a failed deploy — never raises."""
    try:
        from hop3.plugins.email.notifications import (  # ruff:ignore[import-outside-top-level]
            notify,
        )

        reason = str(exc).strip() or type(exc).__name__
        notify(
            "deploy-failure",
            f"Hop3: deploy failed for {app.name}",
            f"Deploying app '{app.name}' failed:\n\n{reason[:2000]}\n\n"
            f"Investigate: hop3 app logs --app {app.name}",
        )
    except Exception:
        # A notification problem must never mask the deploy failure being
        # reported; log it and let the original exception propagate.
        server_log.exception("deploy-failure notification errored", app_name=app.name)


def _do_deploy(  # ruff:ignore[too-many-statements]
    app: App,
    *,
    deltas: dict[str, int] | None = None,
    db_session: Session | None = None,
) -> None:
    """
    Deploys an application using a pluggable builder and deployer.

    This function orchestrates the deployment process:
    1. Parses application configuration (Procfile/hop3.toml).
    1.5. Provisions addons and injects env vars from hop3.toml.
    2. Runs prebuild hook (may fetch source code, prepare environment).
    3. Selects and runs a suitable Builder.
    4. Runs postbuild hook (migrations, asset compilation, etc.).
    5. Selects and runs a suitable Deployer.
    6. (Future) Configures the proxy based on deployment info.

    The prebuild hook runs BEFORE builder selection because it may fetch
    or generate the source code that the builder needs to detect.

    Args:
        app: The application to deploy
        deltas: Optional scaling deltas for workers
        db_session: Database session for addon provisioning (required for auto-provisioning)
    """
    deltas = deltas or {}

    # Reset decision logger for this deployment
    from hop3.lib.decision_log import (  # ruff:ignore[import-outside-top-level]
        flush_decision_logger,
        reset_decision_logger,
    )

    reset_decision_logger()

    # --- 1. Parse Application Configuration ---
    log(f"Starting deployment for app '{app.name}'", level=0, fg="green")
    server_log.info("Starting deployment", app_name=app.name, app_id=app.id)

    try:
        app_config = AppConfig.from_dir(app.app_path)
    except ValueError as e:
        # Raised if Procfile is missing, hop3.toml is malformed, etc.
        abort_with_diagnosis(
            Diagnosis(
                component="Deployer",
                action="parse app configuration",
                reason=str(e),
                hint=("Ensure the app has a valid Procfile or hop3.toml at its root"),
                troubleshooting=[
                    "See docs/src/hop3-toml-reference.md for the schema",
                    f"hop3 app logs --app {app.name}",
                ],
            )
        )

    # Log parsed configuration for debugging
    log(f"Config parsed from: {app_config.app_dir}", level=2)
    log(f"  has_procfile: {app_config.has_procfile}", level=2)
    log(f"  has_hop3_toml: {app_config.has_hop3_toml}", level=2)
    log(f"  workers: {list(app_config.workers.keys())}", level=2)
    if app_config.pre_build:
        log(f"  pre_build: {app_config.pre_build}", level=2)
    if app_config.post_build:
        log(f"  post_build: {app_config.post_build}", level=2)

    # --- 1.5. Process Config-Based Addons and Env Vars ---
    # This runs BEFORE build because some builds need database URLs etc.
    if app_config.has_hop3_toml:
        _process_config_dependencies(app, app_config, db_session)

    # --- 1.6. Prepare the freshly-extracted source tree for the build ---
    _prepare_source_for_build(app, app_config, db_session)

    # --- 2. Run Prebuild Hook ---
    # This runs BEFORE builder selection because prebuild may fetch source code
    # or generate files that the builder needs to detect the app type.
    prebuild_cmd = app_config.pre_build
    if prebuild_cmd:
        log(f"Found prebuild command: {prebuild_cmd}", level=2)
    _run_hook("prebuild", prebuild_cmd, app.src_path)

    # --- 3. Select and Run Builder ---
    context = DeploymentContext(
        app_name=app.name,
        source_path=app.src_path,
        app_config=app_config.to_dict(),
        app=app,
    )

    builder = get_builder(context)
    log(f"Using builder: '{builder.name}'", level=1, fg="blue")

    _enforce_builder_resource_support(app, app_config, builder.name, context)

    build_artifact = builder.build()
    log(
        f"Build successful. Artifact: {build_artifact.location} (kind: {build_artifact.kind})",
        level=1,
        fg="green",
    )

    # --- 3.5. Enhance Artifact with Merged Runtime Config ---
    # RuntimeManifestBuilder merges Procfile and hop3.toml into RuntimeConfig.
    # The toolchain provides env_vars, path_prepend, working_dir; we add:
    # - workers (from Procfile/hop3.toml merged)
    # - before_run (from hop3.toml [run] before-run)
    # - static_paths (from hop3.toml [run] static)
    # - healthcheck_path/timeout (from hop3.toml [run] healthcheck)
    manifest_builder = RuntimeManifestBuilder(app_config)
    enhanced_runtime = manifest_builder.build(
        env_vars=build_artifact.runtime.env_vars,
        path_prepend=build_artifact.runtime.path_prepend,
        working_dir=build_artifact.runtime.working_dir,
        workers=build_artifact.runtime.workers or None,
    )
    build_artifact.runtime = enhanced_runtime

    # --- 3.6. Auto-discover WSGI module for Python apps ---
    if build_artifact.kind in {"python", "buildpack", "virtualenv"}:
        _auto_discover_wsgi(build_artifact, app.src_path)

    log(
        f"Runtime manifest built: {len(enhanced_runtime.workers)} workers, "
        f"{len(enhanced_runtime.before_run)} before-run commands",
        level=2,
    )

    # Persist build artifact for run phase
    artifact_path = app.app_path / "BUILD_ARTIFACT.json"
    build_artifact.save(artifact_path)
    log(f"Build artifact saved to: {artifact_path}", level=2)

    # --- 3.9. Run the recipe's own build steps ---
    # [build].build runs AFTER the toolchain (so compiled assets can rely on
    # installed dependencies) and before after-build. This was parsed and never
    # executed for a long time: eleven catalog apps declared build commands that
    # silently did nothing, and only survived because their toolchain happened to
    # do the equivalent. A declared step that does not run is a lie.
    _run_hook(
        "build",
        app_config.build_steps,
        app.src_path,
        path_prepend=build_artifact.runtime.path_prepend,
    )

    # --- 4. Run Postbuild Hook ---
    # Pass path_prepend from the build artifact so postbuild commands can
    # find binaries from the virtualenv (e.g., "python manage.py collectstatic")
    _run_hook(
        "postbuild",
        app_config.post_build,
        app.src_path,
        path_prepend=build_artifact.runtime.path_prepend,
    )

    # --- 5. Select and Run Deployer ---
    deployer = get_deployer(context, build_artifact)
    log(f"Using deployer: '{deployer.name}'", level=1, fg="blue")

    # The deploy method is now part of the strategy instance
    deployment_info = deployer.deploy(deltas)
    log(
        f"Deployment successful. App running at: {deployment_info}",
        level=1,
        fg="green",
    )

    # --- 6. Update App Model ---
    # Store runtime info so start/stop/status commands know how to handle this app
    _update_app_model(app, deployer.name, deployment_info, app_config)

    # --- 6.5. Open the firewall for declared fixed ports (best-effort) ---
    # Now that the app is confirmed running, allow external ingress to the
    # ports it claimed. Skipped silently when no [[ports]] are declared.
    open_fixed_ports(app, db_session)

    # --- 6.55. Start the LeWAF proxy (ADR 050) ---
    # The app is running and its port is known; bring up the per-app WAF proxy
    # that nginx already points at. Rules were compiled+validated in preflight.
    start_waf_proxy(app, app_config)

    # --- 6.6. Apply native [limits] cgroup caps (ADR 046 §3) ---
    # Post-start: the app's PIDs exist only now. Docker caps were applied by the
    # compose generator at build time; this is the native/Nix path. Strict mode
    # aborts here if the cap can't be enforced (no looks-capped-but-isn't).
    try:
        enforce_native_limits(app, app_config)
    except Abort:
        # The app is RUNNING but its cap couldn't be applied (strict mode). The
        # guarantee is "capped or not running", so don't leave it running uncapped
        # — stop + reap it, then re-raise so the deploy fails loudly.
        log(
            f"Stopping '{app.name}': [limits] could not be enforced (strict mode)",
            level=1,
            fg="red",
        )
        app.stop()
        raise

    # --- 6.7. Bootstrap the initial admin account (ADR 056) ---
    # The app is deployed and its DB addon is provisioned, so the recipe's
    # idempotent [admin].create management command can create the account. Runs
    # once (guarded by the credential's bootstrapped flag) and fails loud.
    _bootstrap_admin_account(app, app_config, build_artifact, deployer.name, db_session)

    # Flush decision log summary
    flush_decision_logger()

    log(f"Deployment for '{app.name}' finished successfully.", level=0, fg="green")

    # Surface the initial admin credential once ever (ADR 056) — after the
    # success line so it is the last thing the operator sees. The helper's
    # `surfaced` flag makes this fire on the first SUCCESSFUL deploy and never
    # re-print the password afterwards.
    if db_session is not None:
        surface_admin_credential(app, db_session)

    # Verify the app actually WORKS, not merely that it started. Runs on every
    # deploy path — web UI, `hop3 deploy`, catalog install, git push — because
    # "it deployed" was repeatedly not the same as "you can log in": apps served
    # their login page perfectly while rejecting every credential. A failure is
    # reported loudly rather than swallowed; the app is left deployed so the
    # operator can inspect it, but the deploy does not claim success it cannot
    # back up.
    _run_deploy_smoke_test(app, db_session)

    server_log.info(
        "Deployment finished successfully",
        app_name=app.name,
        app_id=app.id,
        runtime=deployer.name,
        port=app.port,
        hostname=app.hostname,
    )


def _update_app_model(
    app: App, runtime: str, deployment_info: DeploymentInfo, app_config: AppConfig
) -> None:
    """
    Update the App model with deployment information.

    Args:
        app: The App model instance to update
        runtime: The deployer name (e.g., "docker-compose", "uwsgi")
        deployment_info: DeploymentInfo with port and address
        app_config: Parsed application configuration
    """
    # Update runtime so start/stop commands know how to handle this app
    app.runtime = runtime

    # Update port from deployment info. A port-less deployment (static: nginx
    # serves the files directly) has no worker port — clear any stale value from
    # a prior deploy. Otherwise _app_serves_http() probes that dead port and the
    # deploy fails a health check for a site nginx is actually already serving
    # (the "static deploy fails, then works after a restart" bug).
    app.port = deployment_info.port or 0

    # Update hostname from environment config (from ORM)
    runtime_env = app.get_runtime_env()
    host_name = runtime_env.get("HOST_NAME", "")
    if host_name and host_name != "_":
        app.hostname = host_name

    log(
        f"App '{app.name}' model updated: runtime={runtime}, port={app.port}, "
        f"hostname={app.hostname or '(none)'}",
        level=2,
        fg="blue",
    )

    # A port-less deployment (static — nginx serves the files directly) has no
    # worker process to boot: the deployer configured the proxy synchronously
    # before returning, so the app is already serving. The health check below is
    # for uWSGI/docker workers that start asynchronously; running it on a static
    # app would probe a nonexistent worker port and wrongly fail the deploy.
    if not deployment_info.port:
        log(
            f"App '{app.name}' is served directly by the proxy "
            "(no worker process to wait for).",
            level=1,
            fg="green",
        )
        return

    # The deployer has set the state to RUNNING, but for uWSGI the process
    # starts asynchronously via the emperor. Wait for it to actually be running.
    # This ensures deploy doesn't return until the app is confirmed running.
    # Timeout is configurable via hop3.toml [run.start-timeout] or server's APP_START_TIMEOUT
    timeout = app_config.start_timeout
    log(
        f"Waiting for app '{app.name}' to start (timeout: {timeout}s)...",
        level=1,
        fg="blue",
    )

    healthcheck_path = app_config.hop3_config.healthcheck_path
    healthcheck_contains = app_config.hop3_config.healthcheck_contains
    outcome = _wait_for_app_start(app, timeout, healthcheck_path, healthcheck_contains)
    if outcome.started:
        log(f"App '{app.name}' is now running.", level=1, fg="green")
    else:
        _handle_startup_failure(app, outcome, timeout)


def _bounded_log_excerpt(lines: list[str], head: int = 25, tail: int = 20) -> list[str]:
    """
    Excerpt a crash log so the root error survives truncation.

    A crashing runtime puts the actual error — the exception class and message —
    at the TOP of its traceback (Ruby/Java/Python), while uWSGI throttle/respawn
    noise piles up at the BOTTOM. Showing only the tail (the previous behavior)
    cut the exception off, leaving a deep stack of `from …` frames with no
    message — the rails boot failure was undiagnosable for exactly this reason.
    Show the head AND the tail so both the cause and the latest state survive.
    """
    if len(lines) <= head + tail:
        return lines
    omitted = len(lines) - head - tail
    return [*lines[:head], f"    ... ({omitted} line(s) omitted) ...", *lines[-tail:]]


# Markers of an app's own boot/crash error (lowercased substring match). Kept
# broad on purpose — a one-line "Detected error" hint is best-effort.
_APP_ERROR_MARKERS = (
    "unable to load application",  # puma/rack failed to load the rackup
    "traceback (most recent call last)",  # python
    "caused by:",  # java / jvm
    "could not",
    "cannot find",
    "no such file",
    "not found",  # e.g. `sh: 1: exec: <release binary>: not found`
    "fatal error",
)
# An exception/error class name, e.g. NoMethodError, LoadError,
# ActiveRecord::AdapterNotSpecified, SomeException.
_APP_ERROR_RE = re.compile(r"\b[A-Za-z_][\w.]*(?:Error|Exception|NotSpecified)\b")


def _extract_app_error(log_lines: list[str]) -> str | None:
    """
    Best-effort one-line summary of why an app crashed, from its log.

    The root cause (e.g. "Unable to load application:
    ActiveRecord::AdapterNotSpecified: The `cache` database is not configured")
    lives in the app log, but a deep traceback plus outer-layer truncation can
    push it out of view — the deploy diagnostic then just says "look above",
    where there's nothing left. Surfacing the line *in* the diagnosis (printed
    last, so it survives truncation) shows the operator the actual cause.

    Returns the most recent matching line (trimmed), or None.
    """
    for line in reversed(log_lines):
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if any(m in low for m in _APP_ERROR_MARKERS) or _APP_ERROR_RE.search(stripped):
            return stripped[:200]
    return None


def _is_crash_indicator(line: str) -> bool:
    """
    Check if a log line indicates a crash or error.

    Only matches uWSGI-specific crash indicators, not general application logs.
    Apps often log ERROR messages during normal startup (e.g., "ERROR:app: ..."),
    so we avoid matching generic "error:" patterns which cause false positives.
    """
    line_lower = line.lower()
    # uWSGI-specific crash indicators - these mean the process is actually crashing
    crash_patterns = [
        "throttling",  # uWSGI throttling respawns (app keeps crashing)
        "respawning",  # uWSGI respawning crashed worker
        "fatal error",  # Fatal error (with space to avoid "fatal:" in normal logs)
        "segmentation fault",  # Crash
        "killed",  # Process killed (OOM, etc.)
    ]
    return any(pattern in line_lower for pattern in crash_patterns)


def _process_new_logs(app: App, last_log_lines: int) -> tuple[int, int]:
    """
    Process new log lines, display them, and count crash indicators.

    Returns:
        Tuple of (new_last_log_lines, crash_indicator_count)
    """
    crash_count = 0
    try:
        logs = app.get_logs(lines=50)
        if not logs or len(logs) <= last_log_lines:
            return last_log_lines, 0

        new_lines = logs[last_log_lines:]
        for line in new_lines[-10:]:  # Show at most 10 new lines per check
            line_stripped = line.rstrip()
            log(f"  {line_stripped}", level=1)
            if _is_crash_indicator(line_stripped):
                crash_count += 1

        return len(logs), crash_count
    except Exception:
        return last_log_lines, 0  # Ignore log reading errors


def _app_serves_http(
    app: App,
    healthcheck_path: str,
    timeout: float = 3.0,
    healthcheck_contains: str = "",
) -> bool:
    """
    Whether the app actually answers an HTTP request on its web port.

    A *bound TCP socket* is not proof the app serves: gunicorn (and many
    servers) bind the listen socket in the master process before forking
    workers, so a plain ``connect()`` succeeds the instant the master is up —
    even when the worker is dead or hung and no request is ever answered. Only
    a real HTTP *response* confirms a worker is serving.

    Without ``healthcheck_contains``, any status line (2xx-5xx) counts as
    "serving" — a 400/404/500 still proves a worker produced it; the point is to
    distinguish "serving" from "socket bound but nothing answers".

    With ``healthcheck_contains`` set ([healthcheck].contains), "serving" is
    stricter: the response body must contain that substring. This makes the
    readiness gate content-aware, so a status-only 200 (placeholder, error page,
    wrong app behind the proxy) is NOT mistaken for a healthy deploy.

    Returns True for apps with no web ``port`` (background workers): there is no
    HTTP endpoint to probe, so the process/TCP check is all we can assert.
    """
    if not app.port:
        return True
    path = healthcheck_path or "/"
    if not path.startswith("/"):
        path = "/" + path
    host = getattr(app, "hostname", None) or "localhost"
    conn = http.client.HTTPConnection("127.0.0.1", app.port, timeout=timeout)
    try:
        conn.request("GET", path, headers={"Host": host, "Connection": "close"})
        resp = conn.getresponse()  # raises on timeout/refusal
        if not healthcheck_contains:
            return True  # a status line alone == serving
        # Bounded read: a healthcheck body is small, and the socket timeout
        # already caps a slow/streaming response.
        body = resp.read(262144).decode("utf-8", "replace")
        return healthcheck_contains in body
    except (OSError, http.client.HTTPException):
        return False
    finally:
        conn.close()


@dataclass(frozen=True, slots=True)
class StartOutcome:
    """
    Why the startup wait ended.

    The wait gives up for two unrelated reasons, and a bare ``False`` cannot
    tell them apart: the deadline elapsed, or the app crashed so repeatedly that
    waiting was pointless. Reporting the second as the first produces a message
    claiming a timeout that never happened ("did not respond within 180.0s" for
    a deploy that failed in 11), and offers the one remedy guaranteed not to
    work: raising the timeout.
    """

    started: bool
    crash_looped: bool = False
    elapsed: float = 0.0


def _wait_for_app_start(
    app: App,
    timeout: float,
    healthcheck_path: str = "",
    healthcheck_contains: str = "",
) -> StartOutcome:
    """
    Wait for app to start with fail-fast on repeated crashes.

    Monitors the app status and logs, failing immediately if:
    - uWSGI is throttling respawns (app keeps crashing)
    - Multiple crash/respawn cycles detected
    - Clear error messages in logs (missing config, etc.)

    Readiness for a web app means *answering HTTP*, not merely a listening
    socket: ``check_actual_status()`` returns RUNNING as soon as the port is
    bound, but a bound socket with a dead/hung worker accepts connections and
    never replies. We additionally require an HTTP response (``_app_serves_http``)
    so a "bound but not serving" app is treated as not-ready and fails loud
    instead of being reported as a successful deploy behind a dead proxy target.

    Philosophy: The app is responsible for waiting on dependencies.
    The PaaS should fail fast on unrecoverable errors, not retry blindly.

    Args:
        app: The App model instance
        timeout: Maximum seconds to wait
        healthcheck_path: HTTP path to probe ([healthcheck].path); "" → "/"
        healthcheck_contains: required body substring ([healthcheck].contains);
            "" → any status line counts as serving (no content assertion)

    Returns:
        A StartOutcome saying whether the app started and, if not, whether it
        crash-looped or ran out of time.
    """
    poll_interval = 0.5
    progress_interval = 10.0  # Log progress every 10 seconds
    log_check_interval = 2.0  # Check for new logs every 2 seconds
    deadline = time.time() + timeout
    last_progress = time.time()
    last_log_check = time.time()
    last_log_lines = 0
    crash_indicators = 0
    max_crash_indicators = 3  # Fail fast after this many crash signals

    started_at = time.time()
    while time.time() < deadline:
        actual_state = app.check_actual_status()
        if actual_state == AppStateEnum.RUNNING and _app_serves_http(
            app, healthcheck_path, healthcheck_contains=healthcheck_contains
        ):
            return StartOutcome(started=True, elapsed=time.time() - started_at)

        elapsed = time.time() - (deadline - timeout)

        # Stream new log lines and detect crashes
        if time.time() - last_log_check >= log_check_interval:
            last_log_lines, new_crashes = _process_new_logs(app, last_log_lines)
            crash_indicators += new_crashes

            if crash_indicators >= max_crash_indicators:
                log(
                    f"App '{app.name}' is crashing repeatedly. "
                    "Failing fast instead of waiting for timeout.",
                    level=0,
                    fg="red",
                )
                return StartOutcome(
                    started=False,
                    crash_looped=True,
                    elapsed=time.time() - started_at,
                )

            last_log_check = time.time()

        # Log progress periodically
        if time.time() - last_progress >= progress_interval:
            remaining = deadline - time.time()
            log(
                f"Still waiting for '{app.name}' to start... "
                f"({elapsed:.0f}s elapsed, {remaining:.0f}s remaining)",
                level=1,
                fg="yellow",
            )
            last_progress = time.time()

        time.sleep(poll_interval)

    return StartOutcome(started=False, elapsed=time.time() - started_at)


def _log_runtime_hints(app: App) -> None:
    """Where to look next, depending on what runs the app."""
    log("Troubleshooting hints:", level=0, fg="yellow")
    if app.runtime == "uwsgi":
        log("  - Check uWSGI emperor logs: journalctl -u uwsgi-emperor -n 50", level=0)
        log(
            f"  - Check app uWSGI config: cat /home/hop3/uwsgi-enabled/{app.name}.ini",
            level=0,
        )
    elif app.runtime == "docker-compose":
        log(
            f"  - Check Docker logs: docker compose -f "
            f"{app.src_path}/.hop3-compose.yml logs",
            level=0,
        )
        log("  - Check container status: docker ps -a", level=0)
    log(f"  - View full logs: hop3 app logs --app {app.name}", level=0)


def _handle_startup_failure(app: App, outcome: StartOutcome, timeout: float) -> None:
    """
    Report a failed startup, naming what actually happened.

    Gathers diagnostic information, analyzes logs for common failure patterns,
    and raises an Abort with helpful details.

    Args:
        app: The App model instance
        outcome: Why the wait ended (crash loop vs. elapsed deadline)
        timeout: The configured start timeout
    """
    app.run_state = AppStateEnum.FAILED
    if outcome.crash_looped:
        app.error_message = (
            f"App crashed repeatedly on startup, after {outcome.elapsed:.0f}s"
        )
    else:
        app.error_message = f"App failed to start within {timeout}s timeout"

    # Gather diagnostic information
    headline = (
        f"App '{app.name}' crashed repeatedly and was abandoned after "
        f"{outcome.elapsed:.0f}s."
        if outcome.crash_looped
        else f"App '{app.name}' failed to start within {timeout}s."
    )
    log(headline, level=0, fg="red")
    log("Gathering diagnostic information...", level=1, fg="yellow")

    # Get actual status
    actual_state = app.check_actual_status()
    log(f"  Current actual state: {actual_state.name}", level=0)

    # Reaching here with the port already listening means the socket is bound
    # but the app never answered an HTTP request — the classic "master bound
    # the socket, the worker failed to boot / is hung" shape. Name it, because
    # otherwise "actual state: RUNNING" + "failed to start" reads as a paradox.
    if actual_state == AppStateEnum.RUNNING and getattr(app, "port", None):
        log(
            f"  The app's port ({app.port}) is listening but it did not answer "
            "an HTTP request: the server bound its socket but no worker is "
            "serving (e.g. the worker failed to boot or is hung). This is a "
            "real failure — the app would be unreachable behind the proxy.",
            level=0,
            fg="red",
        )

    # Get recent logs and analyze for common failure patterns
    recent_logs: list[str] = []
    try:
        recent_logs = app.get_logs(lines=200) or []
        if recent_logs:
            log("  Recent log output:", level=0)
            for line in _bounded_log_excerpt(recent_logs):
                log(f"    {line}", level=0)
        else:
            log("  No log output available.", level=0)
    except Exception as e:
        log(f"  Could not retrieve logs: {e}", level=0)

    # Analyze logs for specific failure patterns and provide targeted advice
    log("", level=0)
    _diagnose_failure(app, recent_logs)

    _log_runtime_hints(app)

    # A longer deadline cannot help an app that exits on every respawn, and
    # suggesting it sends the operator to change the one setting that is not
    # the problem.
    raise_timeout = not outcome.crash_looped
    if raise_timeout:
        log(
            "  - Increase timeout in hop3.toml: "
            f"[run] start-timeout = {int(timeout * 2)}",
            level=0,
        )

    if outcome.crash_looped:
        reason = (
            f"'{app.name}' crashed repeatedly on startup and was abandoned after "
            f"{outcome.elapsed:.0f}s; the {timeout:.0f}s timeout was never reached"
        )
    else:
        reason = f"'{app.name}' did not respond to health checks within {timeout}s"

    troubleshooting = [
        f"hop3 app logs --app {app.name}",
        f"hop3 app logs --app {app.name} --build",
    ]
    if raise_timeout:
        troubleshooting.append(
            "Increase start-timeout in hop3.toml: "
            f"[run] start-timeout = {int(timeout * 2)}"
        )

    abort_with_diagnosis(
        Diagnosis(
            component="Deployer",
            action="start app",
            reason=reason,
            hint="See the diagnostics and recent log output above",
            troubleshooting=troubleshooting,
        )
    )


def _diagnose_failure(app: App, log_lines: list[str]) -> None:
    """
    Analyze log lines for common failure patterns and log specific diagnoses.

    This helps users understand *why* the app failed to start, rather than
    just seeing a generic timeout message.
    """
    log_text = "\n".join(log_lines).lower()

    # Load the artifact kind so we can gate WSGI-specific diagnoses on
    # apps that were actually expected to configure a WSGI module. Apps
    # built via nix / go / ruby / docker legitimately run uWSGI in
    # no-workers mode with an attach-daemon; reporting "no-workers" as
    # a failure for those would be a false positive.
    artifact_kind: str | None = None
    try:
        from hop3.core.artifacts import (  # ruff:ignore[import-outside-top-level]
            BuildArtifact,
        )

        artifact = BuildArtifact.load(app.app_path / "BUILD_ARTIFACT.json")
        if artifact is not None:
            artifact_kind = artifact.kind
    except Exception:
        # Missing / unreadable artifact is not fatal for diagnosis; we
        # just skip the WSGI-specific pattern match.
        artifact_kind = None

    wsgi_kinds = {"python", "buildpack", "virtualenv"}

    # Check for uWSGI "no workers" mode (WSGI module not configured)
    if artifact_kind in wsgi_kinds and (
        "operational mode: no-workers" in log_text
        or ("no app loaded" in log_text and "loading" not in log_text)
    ):
        log_diagnosis(
            Diagnosis(
                component="uWSGI",
                action="start workers",
                reason="uWSGI started in no-workers mode (no WSGI module configured)",
                hint=(
                    "Add a WSGI worker to hop3.toml under [run.workers], e.g. "
                    '`wsgi = "app:application"`'
                ),
                troubleshooting=[
                    "See https://hop3.cloud/guides/user-guide/#workers",
                    "hop3 app logs <app> --build",
                ],
            )
        )
        return

    # Check for daemon throttling (repeated crashes)
    if "throttling" in log_text:
        reason = "a daemon is crashing repeatedly; uWSGI is throttling respawns"
        detected = _extract_app_error(log_lines)
        if detected:
            # Put the actual error in the diagnosis itself — it's printed last,
            # so it survives the test runner's "last N lines" truncation, unlike
            # the traceback further up.
            reason += f". Detected error: {detected}"
        log_diagnosis(
            Diagnosis(
                component="uWSGI",
                action="keep daemon running",
                reason=reason,
                hint=(
                    "Look above for 'Error', 'Traceback', or 'Cannot find' lines "
                    "in the daemon's output"
                ),
            )
        )
        return

    # Check for connection refused (common with database/service issues)
    if "econnrefused" in log_text or "connection refused" in log_text:
        log_diagnosis(
            Diagnosis(
                component="App runtime",
                action="connect to a required service",
                reason="the app got 'connection refused' from an addon or upstream",
                hint=(
                    "Check that all addon services (PostgreSQL, MySQL, Redis) "
                    "are running and reachable from this server"
                ),
                troubleshooting=[
                    "hop3 addon list",
                    "systemctl status postgresql mysql redis  (or equivalent)",
                ],
            )
        )
        return

    # Check for missing module/file errors
    if "modulenotfounderror" in log_text or "no such file or directory" in log_text:
        log_diagnosis(
            Diagnosis(
                component="App runtime",
                action="load a required file or module",
                reason="Python raised ModuleNotFoundError or a path was missing",
                hint=(
                    "Check that all dependencies are installed and file paths "
                    "in hop3.toml are correct"
                ),
                troubleshooting=[
                    "hop3 app logs <app> --build  # confirm all pip installs succeeded",
                    "Verify Procfile / hop3.toml entry paths match repo layout",
                ],
            )
        )
        return


def stop_previous_instance(app: App) -> None:
    """
    Stop a still-running previous instance before its source is replaced.

    A redeploy replaces and rebuilds the SAME ``src`` tree the running app uses
    (the upload extractor clears ``src`` first; the build then writes
    ``node_modules``, ``dist``, ``target/*.jar`` there). A live process holding
    those open races every stage: clearing ``src`` deletes a jar the old
    ``java`` still maps, then the rebuild rewrites it — uWSGI respawns the old
    daemon against the half-written file and the next launch reads a truncated
    jar (``NoClassDefFoundError`` / "Invalid or corrupt jarfile"), or `npm`
    can't reconcile a held ``node_modules`` (ENOTEMPTY), or esbuild execs a
    binary still in use (ETXTBSY). Call this BEFORE the source is replaced so
    nothing live contends with it. ``stop()`` reaps and *confirms* the processes
    are gone (raising if any survive even SIGKILL).

    A no-op on a first deploy (the freshly-created app is recorded STOPPED). A
    crashed app (FAILED) is also torn down, since it may still have leftover
    processes holding files.
    """
    if app.run_state in {
        AppStateEnum.RUNNING,
        AppStateEnum.STARTING,
        AppStateEnum.STOPPING,
        AppStateEnum.FAILED,
    }:
        log(
            f"Stopping previous instance of '{app.name}' before rebuild",
            level=1,
            fg="blue",
        )
        app.stop()


def _enforce_builder_resource_support(
    app: App, app_config: AppConfig, builder_name: str, context: DeploymentContext
) -> None:
    """
    Fail loud when declared resources can't be honored by the chosen builder.

    Volumes work on native/Nix but not Docker (ADR 046 §2); limits are resolved
    against the server-wide defaults/ceilings and applied per builder (§3).
    """
    hop3_config = app_config.hop3_config
    _reject_volumes_on_docker(builder_name, hop3_config.volumes)
    _apply_limits(app, hop3_config, builder_name, context)


def _apply_limits(
    app: App,
    hop3_config: Hop3Config,
    builder_name: str,
    context: DeploymentContext,
) -> None:
    """
    Resolve [limits] against the server policy and apply per builder (ADR 046 §3).

    Resolution (declared caps over the operator's server-wide defaults, with a
    value over its ceiling aborting loudly) runs here for *both* builders so a bad
    ceiling fails before the build. Docker stashes the resolved set for the
    compose generator and records ``limits_enforced=docker`` now. Native/Nix
    enforcement needs the app's PIDs, which exist only once it is RUNNING, so it
    happens post-start via ``enforce_native_limits`` — here we only validate.
    """
    declared = hop3_config.limits
    cfg = HopConfig.get_instance()
    try:
        resolved = resolve_limits(
            declared, cfg.limits_defaults(), cfg.limits_ceilings()
        )
    except LimitsError as e:
        abort_with_diagnosis(
            Diagnosis(
                component="Limits",
                action="apply [limits]",
                reason=str(e),
                hint="Lower the cap, or adjust the server-wide [limits] policy.",
                troubleshooting=["See ADR 046 §3 (resource caps)"],
            )
        )

    if resolved.is_empty():
        return

    if builder_name.lower() == "docker":
        # Hand the resolved caps to the compose generator (it reads this dict),
        # and record the enforced state for status.
        context.app_config["hop3_config"]["limits"] = resolved.as_dict()
        app.limits_enforced = "docker"
        app.limits_detail = format_limits_detail(resolved.as_dict())
    # Native/Nix: the cap is applied post-start (enforce_native_limits); the
    # resolve above already aborted on a ceiling breach, before the build.


def _reject_volumes_on_docker(builder_name: str, volumes: list[dict[str, Any]]) -> None:
    """
    Abort the deploy if [[volumes]] are declared under the Docker builder.

    Volumes are realized as host-side symlinks into src/ (ADR 046 §2), which a
    Docker container cannot see — and the generated compose has no bind-mount
    for them — so the app's data would be silently lost. Fail loud instead.
    Native/Nix run on the host with cwd=src, so the symlink resolves there.
    """
    if builder_name.lower() == "docker" and volumes:
        msg = (
            "[[volumes]] is not yet supported for Docker-deployed apps: the "
            "container cannot see the host volume, so data would be lost. Use "
            "the native or nix builder, or remove the [[volumes]] declaration."
        )
        raise ValueError(msg)


def _prepare_source_for_build(
    app: App, app_config: AppConfig, db_session: Session | None
) -> None:
    """
    Ready the freshly-extracted source tree before the prebuild/build runs.

    Three ordered steps, all before any build output is produced:

    1. **Claim declared fixed ports.** Non-HTTP services (SMTP, XMPP, RTMP, …)
       bind a host port directly; only one app can own it. Claiming here fails
       fast with a clear error if another app holds it, and rolls back with the
       deploy session on failure.
    2. **Stop the previous instance** (safety net). The primary stop happens
       before the source is replaced (in DeployCmd / the git hooks), where the
       destructive race is — clearing src/ deletes build outputs the old process
       holds. This covers any do_deploy path that didn't already stop (e.g.
       restart); it's a no-op when the app is already stopped.
    3. **Realize declarative volumes** ([[volumes]]). Link persistent volumes into
       src/ before any build/run writes to them. Storage lives under
       <app>/volumes/, outside src/, so it survives the redeploy that wipes src/
       (ADR 046 §2). No-op when none are declared.
    """
    claim_fixed_ports(app, app_config, db_session)
    # Compile + validate the [waf] policy and allocate the proxy port now, so the
    # nginx config generated during deploy points at the WAF proxy (ADR 050 §7).
    # Aborts the deploy loudly on an invalid policy (compile-before-commit, §5).
    configure_waf_preflight(app, app_config, db_session)
    stop_previous_instance(app)
    realize_volumes(app, app_config.hop3_config.volumes)


def _process_config_dependencies(
    app: App, app_config: AppConfig, db_session: Session | None
) -> None:
    """
    Process addons and env vars from hop3.toml.

    This provisions any required backing services and injects
    environment variables before the build phase.

    Args:
        app: The application model
        app_config: Parsed application configuration
        db_session: Database session for persistence (required for addon provisioning)
    """
    hop3_config = app_config.hop3_config

    if db_session is None:
        log(
            "  Warning: No db_session provided - skipping addon provisioning",
            level=0,
            fg="yellow",
        )
        server_log.warning(
            "No db_session provided for addon provisioning", app_name=app.name
        )
        return

    # Provision addons from [[addons]] sections
    addon_configs = hop3_config.addons
    if addon_configs:
        log(
            f"Processing {len(addon_configs)} addon(s) from hop3.toml...",
            level=1,
            fg="blue",
        )
        provision_addons(app, addon_configs, db_session)

    # Re-derive env from EVERY attached addon (declared above OR attached
    # manually via `hop3 addon attach`), so DATABASE_URL/REDIS_URL/... are
    # re-injected from the stored credentials on each deploy and can't silently
    # go missing on redeploy. Runs unconditionally — a manually-attached addon
    # leaves no [[addons]] entry, so this is its only re-injection point.
    reinject_attached_addons(app, db_session)

    # Inject env vars from [env] section
    env_config = hop3_config.env
    if env_config:
        env_policy = hop3_config.env_policy
        log(
            f"Processing {len(env_config)} env var(s) from hop3.toml "
            f"(policy: {env_policy})...",
            level=1,
            fg="blue",
        )
        set_default_env_vars(app, env_config, db_session, env_policy=env_policy)

    # Generate declared secrets ([env] { generate = ... }) — once, for any var
    # still unset. Runs after static [env] and before [env.computed] so a
    # computed value may reference a generated secret via ${VAR} (ADR 046).
    generated_config = hop3_config.env_generated
    if generated_config:
        log(
            f"Generating {len(generated_config)} secret(s) from [env]...",
            level=1,
            fg="blue",
        )
        set_generated_env_vars(app, generated_config, db_session)

    # Translate [domains].list into HOST_NAME. Schema already rejects mixing
    # with env.HOST_NAME and combining "_" with other hosts, but we re-check
    # defensively (HOP3_SKIP_CONFIG_VALIDATION can bypass schema in dev).
    domains_config = hop3_config.domains
    if domains_config:
        _apply_domains_to_host_name(
            app, domains_config, hop3_config.domains_policy, db_session
        )

    # Translate [deploy].allow-http into the canonical flag every proxy reads
    # (nginx/caddy/traefik share it via should_redirect_to_https), so the recipe
    # declares the intent once regardless of which proxy is installed. Written
    # on every deploy rather than keep-existing, so dropping `allow-http` from
    # the recipe actually restores the redirect.
    set_env_vars(app, {ALLOW_HTTP_KEY: str(hop3_config.allow_http).lower()}, db_session)

    # Expose the app's canonical public URL (HOP3_PUBLIC_URL = https://<host>)
    # now that HOST_NAME is settled, so recipes can reference ${HOP3_PUBLIC_URL}
    # in the env refs / computed steps below within this same deploy.
    set_public_url_env(app, db_session)

    # Bootstrap the app's admin account (ADR 056): generate the password once,
    # resolve the email, persist the encrypted credential, and inject the
    # canonical HOP3_ADMIN_* vars — before refs/computed so a recipe can map
    # them into app-specific names. The account itself is created post-deploy.
    provision_admin_credential(app, hop3_config.admin, db_session)

    # Mint the Hop3-owned probe password too, so the app's smoke test can sign
    # in with an account the operator never touches (see probe_account).
    provision_probe_credential(app, hop3_config.probe, db_session)

    # Resolve dynamic [env] references ({ from, key } / app facts). Runs after
    # the domains -> HOST_NAME step so a { key = "domain" } ref can see it, and
    # before [env.computed] so a computed value can interpolate a ref (ADR 046).
    refs_config = hop3_config.env_refs
    if refs_config:
        log(
            f"Resolving {len(refs_config)} env reference(s)...",
            level=1,
            fg="blue",
        )
        resolve_env_refs(app, refs_config, db_session)

    # Resolve computed env vars from [env.computed] section
    computed_config = hop3_config.env_computed
    if computed_config:
        log(
            f"Resolving {len(computed_config)} computed env var(s)...",
            level=1,
            fg="blue",
        )
        set_computed_env_vars(app, computed_config, db_session)

    # Commit changes before continuing with build
    if any((
        addon_configs,
        env_config,
        generated_config,
        refs_config,
        domains_config,
        hop3_config.admin,
    )):
        db_session.commit()
        server_log.info(
            "Config dependencies processed",
            app_name=app.name,
            addon_count=len(addon_configs),
            env_var_count=len(env_config),
            domain_count=len(domains_config),
        )


def _apply_domains_to_host_name(
    app: App,
    domains_config: list[str],
    policy: str,
    db_session: Session,
) -> None:
    """
    Translate [domains].list into the HOST_NAME env var.

    Validates each hostname, rejects "_" combined with other hosts, and
    aborts the deploy on a cross-app conflict. Mirrors set_default_env_vars
    semantics via the env_policy argument: "keep-existing" leaves a manually
    set HOST_NAME alone; "override" updates it every deploy.
    """
    try:
        validated = [validate_hostname(h) for h in domains_config]
    except InvalidIdentifierError as e:
        abort_with_diagnosis(
            Diagnosis(
                component="hop3.toml",
                action="apply [domains].list",
                reason=str(e),
                hint=(
                    "Each entry in [domains].list must be a valid RFC-1123 hostname."
                ),
            )
        )

    if "_" in validated and len(validated) > 1:
        abort_with_diagnosis(
            Diagnosis(
                component="hop3.toml",
                action="apply [domains].list",
                reason=(
                    "The catch-all hostname '_' cannot be combined with "
                    "other hostnames in [domains].list."
                ),
                hint="Use '_' on its own, or list specific hostnames.",
            )
        )

    conflict = check_hostname_conflict(db_session, app.name, validated)
    if conflict:
        other_app, other_host = conflict
        abort_with_diagnosis(
            Diagnosis(
                component="hop3.toml",
                action="apply [domains].list",
                reason=(
                    f"Hostname '{other_host}' is already bound to app '{other_app}'."
                ),
                hint=(
                    "Remove the conflicting hostname from one of the apps "
                    "(see `hop3 domain list <app>`)."
                ),
            )
        )

    log(
        f"Processing {len(validated)} domain(s) from hop3.toml (policy: {policy})...",
        level=1,
        fg="blue",
    )
    set_default_env_vars(
        app, {"HOST_NAME": " ".join(validated)}, db_session, env_policy=policy
    )


def _bootstrap_admin_account(
    app: App,
    app_config: AppConfig,
    build_artifact: BuildArtifact,
    deployer_name: str,
    db_session: Session | None,
) -> None:
    """
    Run the recipe's [admin].create once, post-deploy (ADR 056, native path).

    The create command runs in the app's source dir with the app's runtime env
    (HOP3_ADMIN_* + DATABASE_URL) and the build's PATH prepended, so a
    management command (e.g. Django ``createsuperuser``) reaches the provisioned
    DB. Docker-Compose apps do not run recipe commands here; if such an app
    declares ``[admin].create`` we abort loudly rather than silently skip it —
    the app must self-bootstrap from the injected env in its entrypoint.
    """
    has_toml = app_config.has_hop3_toml
    admin = app_config.hop3_config.admin if has_toml else {}
    probe = app_config.hop3_config.probe if has_toml else {}
    # ONLY when something declares a `create` command. A [probe] without one is
    # a recipe saying "the app makes this account itself", and that turned out
    # not to be a claim Hop3 can act on: opening this gate so such a probe was
    # offered to the smoke test took matomo from PASS to FAIL in one run, and
    # left uptime-kuma failing exactly as before. Both apps' own bootstraps were
    # supposed to create the account; neither produced one that authenticates.
    #
    # So Hop3 offers the check only a probe it created and watched succeed.
    # Otherwise the check uses the operator's credential and REPORTS that it did
    # ("verified the handover only"), which is a weaker claim, not a silent one.
    wants_create = bool(admin.get("create")) or bool(probe.get("create"))
    if not wants_create or db_session is None:
        return

    if "docker" in deployer_name:
        msg = (
            f"[admin].create is not supported for the Docker app '{app.name}': "
            "recipe commands do not run on the compose path. Bootstrap the admin "
            "in the container entrypoint from the injected "
            "HOP3_ADMIN_USER/EMAIL/PASSWORD env, and drop [admin].create."
        )
        raise AdminBootstrapError(msg)

    path_prepend = build_artifact.runtime.path_prepend

    def run_create(command: str) -> None:
        env = {**os.environ, **app.get_runtime_env()}
        if path_prepend:
            extra = ":".join(p for p in path_prepend if p)
            if extra:
                env["PATH"] = f"{extra}:{env.get('PATH', '')}"
        result = shell(command, cwd=app.src_path, env=env, check=False)
        if result.returncode:
            # Include what the command actually said. Reporting only the exit
            # status leaves the operator (and the next deploy) with nothing to
            # act on — the failure is loud but useless.
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            detail = f"\n{output[-1500:]}" if output else " (no output)"
            msg = f"exit status {result.returncode}: {command}{detail}"
            raise AdminBootstrapError(msg)

    bootstrap_admin_account(app, admin, db_session, run_create)
    bootstrap_probe_account(app, probe, db_session, run_create)


def _run_hook(
    hook_name: str,
    commands: list[str],
    cwd: Path,
    path_prepend: list[str] | None = None,
) -> None:
    """
    Run a deployment hook (prebuild/postbuild).

    Args:
        hook_name: Name of the hook for logging (e.g., "prebuild", "postbuild")
        commands: List of shell commands to execute sequentially
        cwd: Working directory for the commands
        path_prepend: Paths to prepend to PATH (e.g., virtualenv bin directory)

    Raises:
        Abort: If any command fails with non-zero exit code
    """
    if not commands:
        return

    # Build environment with prepended paths (e.g., virtualenv bin)
    env = dict(os.environ)
    if path_prepend:
        extra = ":".join(p for p in path_prepend if p)
        if extra:
            env["PATH"] = f"{extra}:{env.get('PATH', '')}"
            log(f"  PATH prepended with: {extra}", level=2)

    log(f"Running {hook_name}...", level=1, fg="blue")
    for command in commands:
        log(f"  {command}", level=2)
        result = shell(command, cwd=cwd, env=env)
        if result.returncode:
            abort_with_diagnosis(
                Diagnosis(
                    component="Deployer",
                    action=f"run {hook_name}",
                    reason=(
                        f"command exited with status {result.returncode}: {command}"
                    ),
                    hint=(
                        f"Check the '{hook_name}' entry in hop3.toml — it "
                        "should run cleanly in the app source directory"
                    ),
                    troubleshooting=[
                        f"cd {cwd} && {command}",
                        "Review the command output above",
                    ],
                )
            )


def _auto_discover_wsgi(artifact: BuildArtifact, src_path: Path) -> None:
    """
    Auto-discover WSGI module for Python apps that have no web workers.

    Probes for common WSGI entry points and adds a 'wsgi' worker to the
    artifact's runtime config if found.

    Args:
        artifact: The build artifact to potentially modify
        src_path: Path to the application source code
    """
    web_worker_names = {"wsgi", "jwsgi", "rwsgi", "web"}
    if any(w in web_worker_names for w in artifact.runtime.workers):
        return  # Already has a web-facing worker

    # Probe for common WSGI entry points (ordered by convention)
    probes = [
        # (file_to_check, wsgi_module_string, description)
        ("wsgi.py", "wsgi:application", "wsgi.py"),
        ("app.py", "app:app", "app.py"),
    ]

    # Django convention: <project>/wsgi.py
    for child in sorted(src_path.iterdir()):
        if child.is_dir() and (child / "wsgi.py").exists():
            module = f"{child.name}.wsgi:application"
            probes.append((
                str(child / "wsgi.py"),
                module,
                f"{child.name}/wsgi.py (Django)",
            ))
            break

    for file_check, module, description in probes:
        if (src_path / file_check).exists():
            log(
                f"  Auto-detected WSGI module: {module} (from {description})",
                level=1,
                fg="green",
            )
            artifact.runtime.workers["wsgi"] = module
            return


def _run_deploy_smoke_test(app: App, db_session: Session | None) -> None:
    """
    Run the app's check.py at the end of a deploy and report what it found.

    Silent about apps that ship no check — most do not, and saying so on every
    deploy would be noise. Loud in both other cases: a pass is stated so the
    operator knows the app was actually exercised, and a failure names the app
    and shows the check's own output.

    Deliberately does NOT abort the deploy. The app is already built, started
    and healthy by this point; tearing that down over a smoke test would turn a
    diagnosable app into no app at all. What must not happen is a deploy that
    stays silent about it.
    """
    if db_session is None:
        return

    from hop3.server.checks.runner import (  # ruff:ignore[import-outside-top-level]
        run_app_check,
    )

    try:
        outcome = run_app_check(app, db_session)
    except Exception as e:
        # A broken check must not be mistaken for a broken app, nor hide itself.
        log(f"Smoke test could not run for '{app.name}': {e}", level=0, fg="yellow")
        server_log.warning("smoke test errored", app_name=app.name, error=str(e))
        return

    if not outcome.ran:
        return

    if outcome.passed:
        log(
            f"Smoke test passed for '{app.name}' — {outcome.summary}.",
            level=0,
            fg="green",
        )
        server_log.info(
            "smoke test passed",
            app_name=app.name,
            used_hop3_account=outcome.used_hop3_account,
        )
        return

    log(
        f"Smoke test FAILED for '{app.name}' — it is deployed and running, but "
        f"did not pass its own verification:",
        level=0,
        fg="red",
    )
    for line in outcome.output.splitlines():
        log(f"  {line}", level=0, fg="red")
    log(
        f"Investigate with: hop3 app check --app {app.name}",
        level=0,
        fg="yellow",
    )
    server_log.warning("smoke test failed", app_name=app.name, output=outcome.output)
