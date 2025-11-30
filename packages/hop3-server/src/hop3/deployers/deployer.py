# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.plugins import get_builder, get_deployment_strategy
from hop3.core.protocols import DeploymentContext
from hop3.lib import Abort, log
from hop3.project.config import AppConfig

if TYPE_CHECKING:
    from hop3.orm.app import App

__all__ = ["do_deploy"]


def do_deploy(app: App, *, deltas: dict[str, int] | None = None) -> None:
    """
    Deploys an application using a pluggable builder and deployer.

    This function orchestrates the deployment process:
    1. Sets up a context object with app information.
    2. Asks the plugin system for a suitable Builder.
    3. Executes the build to get a BuildArtifact.
    4. Asks the plugin system for a suitable Deployer.
    5. Executes the deployment.
    6. (Future) Configures the proxy based on deployment info.
    """
    deltas = deltas or {}

    # --- 1. Create Deployment Context ---
    log(f"Starting deployment for app '{app.name}'", level=0, fg="green")

    try:
        app_config = AppConfig.from_dir(app.app_path)
    except ValueError as e:
        # Raised if Procfile is missing, etc.
        raise Abort(str(e))

    context = DeploymentContext(
        app_name=app.name,
        source_path=app.src_path,
        app_config=app_config.to_dict(),
        app=app,
    )

    # --- 2. Select and Run Builder ---
    builder = get_builder(context)
    log(f"Using builder: '{builder.name}'", level=1, fg="blue")
    build_artifact = builder.build()
    log(
        f"Build successful. Artifact: {build_artifact.location} (kind: {build_artifact.kind})",
        level=1,
        fg="green",
    )

    # --- 3. Select and Run Deployment Strategy ---
    deployer = get_deployment_strategy(context, build_artifact)
    log(f"Using deployment strategy: '{deployer.name}'", level=1, fg="blue")

    # The deploy method is now part of the strategy instance
    deployment_info = deployer.deploy(deltas)
    log(
        f"Deployment successful. App running at: {deployment_info}",
        level=1,
        fg="green",
    )

    # --- 4. Configure Proxy (Future Step) ---
    # pm = get_plugin_manager()
    # proxy_strategy = pm.hook.get_proxy_strategy(...)
    # proxy_strategy.configure(app, deployment_info)
    # log("Proxy configured successfully.", level=1)

    # except (RuntimeError, Abort) as e:
    #     # Catch errors from strategy selection or execution
    #     log(f"Deployment failed: {e}", fg="red")
    #     msg = f"Deployment failed: {e}"
    #     raise Abort(msg)

    log(f"Deployment for '{app.name}' finished successfully.", level=0, fg="green")
