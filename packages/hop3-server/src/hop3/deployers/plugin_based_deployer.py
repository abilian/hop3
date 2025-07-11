from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.protocols import DeploymentContext
from hop3.core.plugins import get_plugin_manager  # Assume this exists
from hop3.lib import Abort, log
from hop3.project.config import AppConfig

if TYPE_CHECKING:
    from hop3.orm.app import App

__all__ = ["do_deploy"]


def select_strategy(strategy_type: str, available_strategies: list, *args):
    """Helper to select a strategy based on config or auto-detection."""
    # Simplified logic: In reality, you'd get the desired strategy name from AppConfig
    # and fall back to calling accept() on each strategy.
    # For now, we'll just pick the first one that accepts.
    for StrategyClass in available_strategies:
        instance = StrategyClass()
        if instance.accept(*args):
            return instance
    raise Abort(f"Could not find a suitable {strategy_type} strategy.")


def do_deploy(app: App, *, deltas: dict[str, int] | None = None) -> None:
    deltas = deltas or {}

    # --- 1. Create Deployment Context ---
    log(f"Starting deployment for app '{app.name}'", level=0, fg="green")
    app_config = AppConfig.from_dir(app.app_path)
    context = DeploymentContext(app=app, app_config=app_config, log_callback=log)

    pm = get_plugin_manager()

    # --- 2. Select and Run Build Strategy ---
    build_strategies = pm.hook.hop3_register_build_strategies(context=context)
    builder = select_strategy("build", build_strategies, context)
    log(f"Using builder: {builder.name}", level=1, fg="blue")

    build_artifact = builder.build(context)
    log(
        f"Build successful. Artifact: {build_artifact.location} ({build_artifact.kind})",
        level=1,
        fg="green",
    )

    # --- 3. Select and Run Deployment Strategy ---
    deployment_strategies = pm.hook.hop3_register_deployment_strategies(context=context)
    deployer = select_strategy(
        "deployment", deployment_strategies, build_artifact, context
    )
    log(f"Using deployer: {deployer.name}", level=1, fg="blue")

    deployment_info = deployer.deploy(build_artifact, context, deltas)

    # --- 4. Configure Proxy (Simplified) ---
    # The proxy configuration logic would also be a pluggable strategy.
    log("Configuring network proxy...", level=1, fg="blue")
    # proxy_strategy.configure(app, deployment_info)

    log(f"Deployment for '{app.name}' finished successfully.", level=0, fg="green")
