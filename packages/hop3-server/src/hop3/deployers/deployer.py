# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from hop3.core.plugins import get_builder, get_deployment_strategy
from hop3.core.protocols import DeploymentContext
from hop3.lib import Abort, log, shell
from hop3.lib.logging import server_log
from hop3.orm.app import AppStateEnum
from hop3.project.config import AppConfig

if TYPE_CHECKING:
    from hop3.orm.app import App

__all__ = ["do_deploy"]


def do_deploy(app: App, *, deltas: dict[str, int] | None = None) -> None:
    """
    Deploys an application using a pluggable builder and deployer.

    This function orchestrates the deployment process:
    1. Parses application configuration (Procfile/hop3.toml).
    2. Runs prebuild hook (may fetch source code, prepare environment).
    3. Selects and runs a suitable Builder.
    4. Runs postbuild hook (migrations, asset compilation, etc.).
    5. Selects and runs a suitable Deployer.
    6. (Future) Configures the proxy based on deployment info.

    The prebuild hook runs BEFORE builder selection because it may fetch
    or generate the source code that the builder needs to detect.
    """
    deltas = deltas or {}

    # --- 1. Parse Application Configuration ---
    log(f"Starting deployment for app '{app.name}'", level=0, fg="green")
    server_log.info("Starting deployment", app_name=app.name, app_id=app.id)

    try:
        app_config = AppConfig.from_dir(app.app_path)
    except ValueError as e:
        # Raised if Procfile is missing, etc.
        raise Abort(str(e))

    # Log parsed configuration for debugging
    log(f"Config parsed from: {app_config.app_dir}", level=2)
    log(f"  has_procfile: {app_config.has_procfile}", level=2)
    log(f"  has_hop3_toml: {app_config.has_hop3_toml}", level=2)
    log(f"  workers: {list(app_config.workers.keys())}", level=2)
    if app_config.pre_build:
        log(f"  pre_build: {app_config.pre_build}", level=2)
    if app_config.post_build:
        log(f"  post_build: {app_config.post_build}", level=2)

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

    # --- 4. Run Postbuild Hook ---
    _run_hook("postbuild", app_config.post_build, app.src_path)

    # --- 5. Select and Run Deployment Strategy ---
    deployer = get_deployment_strategy(context, build_artifact)
    log(f"Using deployment strategy: '{deployer.name}'", level=1, fg="blue")

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
    timeout = 30.0  # 30 seconds should be enough for most apps
    log(
        f"Waiting for app '{app.name}' to start (timeout: {timeout}s)...",
        level=1,
        fg="blue",
    )

    if app.wait_for_actual_state(
        AppStateEnum.RUNNING, timeout=timeout, poll_interval=0.5
    ):
        log(f"App '{app.name}' is now running.", level=1, fg="green")
    else:
        # App didn't start within timeout - mark as failed
        app.run_state = AppStateEnum.FAILED
        error_msg = f"App failed to start within {timeout}s timeout"
        app.error_message = error_msg
        log(
            f"App '{app.name}' failed to start within {timeout}s. "
            "Check logs with 'hop3 app:logs' for details.",
            level=0,
            fg="red",
        )
        raise Abort(error_msg)


def _run_hook(hook_name: str, command: str, cwd: Path) -> None:
    """Run a deployment hook (prebuild/postbuild).

    Args:
        hook_name: Name of the hook for logging (e.g., "prebuild", "postbuild")
        command: Shell command to execute
        cwd: Working directory for the command

    Raises:
        Abort: If the command fails with non-zero exit code
    """
    if not command:
        return

    log(f"Running {hook_name}...", level=1, fg="blue")
    result = shell(command, cwd=cwd)
    if result.returncode:
        msg = f"{hook_name} failed with exit code {result.returncode}"
        raise Abort(msg, result.returncode)
