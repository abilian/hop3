# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from hop3.core.manifest import RuntimeManifestBuilder
from hop3.core.plugins import get_builder, get_deployer
from hop3.core.protocols import DeploymentContext
from hop3.deployers.addon_provisioning import provision_addons
from hop3.deployers.env_provisioning import set_computed_env_vars, set_default_env_vars
from hop3.lib import Diagnosis, abort_with_diagnosis, log, shell
from hop3.lib.logging import server_log
from hop3.orm.app import AppStateEnum
from hop3.project.config import AppConfig

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session

    from hop3.core.artifacts import BuildArtifact
    from hop3.orm.app import App

__all__ = ["do_deploy"]


def do_deploy(
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
    from hop3.lib.decision_log import (  # noqa: PLC0415
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
                    f"hop3 app logs {app.name}",
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

    # Flush decision log summary
    flush_decision_logger()

    log(f"Deployment for '{app.name}' finished successfully.", level=0, fg="green")
    server_log.info(
        "Deployment finished successfully",
        app_name=app.name,
        app_id=app.id,
        runtime=deployer.name,
        port=app.port,
        hostname=app.hostname,
    )


def _update_app_model(
    app: App, runtime: str, deployment_info, app_config: AppConfig
) -> None:
    """Update the App model with deployment information.

    Args:
        app: The App model instance to update
        runtime: The deployer name (e.g., "docker-compose", "uwsgi")
        deployment_info: DeploymentInfo with port and address
        app_config: Parsed application configuration
    """
    # Update runtime so start/stop commands know how to handle this app
    app.runtime = runtime

    # Update port from deployment info
    if deployment_info.port:
        app.port = deployment_info.port

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

    if _wait_for_app_start(app, timeout):
        log(f"App '{app.name}' is now running.", level=1, fg="green")
    else:
        # App didn't start within timeout - gather diagnostics and fail
        _handle_startup_timeout(app, timeout)


def _is_crash_indicator(line: str) -> bool:
    """Check if a log line indicates a crash or error.

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
    """Process new log lines, display them, and count crash indicators.

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


def _wait_for_app_start(app: App, timeout: float) -> bool:
    """Wait for app to start with fail-fast on repeated crashes.

    Monitors the app status and logs, failing immediately if:
    - uWSGI is throttling respawns (app keeps crashing)
    - Multiple crash/respawn cycles detected
    - Clear error messages in logs (missing config, etc.)

    Philosophy: The app is responsible for waiting on dependencies.
    The PaaS should fail fast on unrecoverable errors, not retry blindly.

    Args:
        app: The App model instance
        timeout: Maximum seconds to wait

    Returns:
        True if app started successfully, False if timed out or crashed
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

    while time.time() < deadline:
        actual_state = app.check_actual_status()
        if actual_state == AppStateEnum.RUNNING:
            return True

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
                return False

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

    return False


def _handle_startup_timeout(app: App, timeout: float) -> None:
    """Handle app startup timeout with diagnostics.

    Gathers diagnostic information, analyzes logs for common failure patterns,
    and raises an Abort with helpful details.

    Args:
        app: The App model instance
        timeout: The timeout that was exceeded
    """
    # Mark app as failed
    app.run_state = AppStateEnum.FAILED
    app.error_message = f"App failed to start within {timeout}s timeout"

    # Gather diagnostic information
    log(f"App '{app.name}' failed to start within {timeout}s.", level=0, fg="red")
    log("Gathering diagnostic information...", level=1, fg="yellow")

    # Get actual status
    actual_state = app.check_actual_status()
    log(f"  Current actual state: {actual_state.name}", level=0)

    # Get recent logs and analyze for common failure patterns
    recent_logs: list[str] = []
    try:
        recent_logs = app.get_logs(lines=30) or []
        if recent_logs:
            log("  Recent log output:", level=0)
            for line in recent_logs[-20:]:  # Show last 20 lines (was 10)
                log(f"    {line}", level=0)
        else:
            log("  No log output available.", level=0)
    except Exception as e:
        log(f"  Could not retrieve logs: {e}", level=0)

    # Analyze logs for specific failure patterns and provide targeted advice
    log("", level=0)
    _diagnose_failure(app, recent_logs)

    # Provide general hints based on runtime
    log("Troubleshooting hints:", level=0, fg="yellow")
    if app.runtime == "uwsgi":
        log("  - Check uWSGI emperor logs: journalctl -u uwsgi-emperor -n 50", level=0)
        log(
            f"  - Check app uWSGI config: cat /home/hop3/uwsgi-enabled/{app.name}.ini",
            level=0,
        )
    elif app.runtime == "docker-compose":
        log(
            f"  - Check Docker logs: docker compose -f {app.src_path}/.hop3-compose.yml logs",
            level=0,
        )
        log("  - Check container status: docker ps -a", level=0)
    log(f"  - View full logs: hop3 app logs {app.name}", level=0)
    log(
        f"  - Increase timeout in hop3.toml: [run] start-timeout = {int(timeout * 2)}",
        level=0,
    )

    abort_with_diagnosis(
        Diagnosis(
            component="Deployer",
            action="start app",
            reason=(f"'{app.name}' did not respond to health checks within {timeout}s"),
            hint="See the diagnostics and recent log output above",
            troubleshooting=[
                f"hop3 app logs {app.name}",
                f"hop3 app build-logs {app.name}",
                (
                    "Increase start-timeout in hop3.toml: "
                    f"[run] start-timeout = {int(timeout * 2)}"
                ),
            ],
        )
    )


def _diagnose_failure(app: App, log_lines: list[str]) -> None:
    """Analyze log lines for common failure patterns and log specific diagnoses.

    This helps users understand *why* the app failed to start, rather than
    just seeing a generic timeout message.
    """
    log_text = "\n".join(log_lines).lower()

    # Check for uWSGI "no workers" mode (WSGI module not configured)
    if "operational mode: no-workers" in log_text or (
        "no app loaded" in log_text and "loading" not in log_text
    ):
        log(
            "Diagnosis: uWSGI started with no workers configured.",
            level=0,
            fg="red",
        )
        log(
            "  Fix: Add a WSGI worker to hop3.toml, e.g.:",
            level=0,
        )
        log("    [run.workers]", level=0)
        log('    wsgi = "app:application"', level=0)
        log("", level=0)
        return

    # Check for daemon throttling (repeated crashes)
    if "throttling" in log_text:
        log(
            "Diagnosis: A daemon process is crashing repeatedly. "
            "uWSGI is throttling respawns.",
            level=0,
            fg="red",
        )
        log(
            "  The daemon's error output may be above. Look for lines "
            "containing 'Error', 'Traceback', or 'Cannot find'.",
            level=0,
        )
        log("", level=0)
        return

    # Check for connection refused (common with database/service issues)
    if "econnrefused" in log_text or "connection refused" in log_text:
        log(
            "Diagnosis: The app could not connect to a required service.",
            level=0,
            fg="red",
        )
        log(
            "  Check that all addon services (PostgreSQL, MySQL, Redis) "
            "are running and accessible.",
            level=0,
        )
        log("", level=0)
        return

    # Check for missing module/file errors
    if "modulenotfounderror" in log_text or "no such file or directory" in log_text:
        log(
            "Diagnosis: A required file or module was not found.",
            level=0,
            fg="red",
        )
        log(
            "  Check that all dependencies are installed and file paths "
            "in hop3.toml are correct.",
            level=0,
        )
        log("", level=0)
        return


def _process_config_dependencies(
    app: App, app_config: AppConfig, db_session: Session | None
) -> None:
    """Process addons and env vars from hop3.toml.

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
    if addon_configs or env_config:
        db_session.commit()
        server_log.info(
            "Config dependencies processed",
            app_name=app.name,
            addon_count=len(addon_configs),
            env_var_count=len(env_config),
        )


def _run_hook(
    hook_name: str,
    commands: list[str],
    cwd: Path,
    path_prepend: list[str] | None = None,
) -> None:
    """Run a deployment hook (prebuild/postbuild).

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
    """Auto-discover WSGI module for Python apps that have no web workers.

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
