# Copyright (c) 2025, Abilian SAS
"""Runtime strategy registry for deployment backends.

.. deprecated:: 0.2.0
    This module is deprecated. Use `hop3.core.plugins.get_deployer_by_name()` instead.
    The hardcoded registry approach has been replaced with plugin-based discovery.

    Migration guide:
        Old code::

            from hop3.core.runtime_registry import get_deployment_strategy
            strategy = get_deployment_strategy(app)

        New code::

            from hop3.core.plugins import get_deployer_by_name
            strategy = get_deployer_by_name(app, app.runtime)

    The plugin-based approach provides:
    - Single source of truth (no duplicate registrations)
    - Automatic discovery via pluggy
    - Support for external plugins
    - Consistent with other strategy types (build, service, proxy)

This module is kept for backwards compatibility but will be removed in v0.3.0.

Supported runtimes:
- uwsgi: uWSGI emperor-based deployment (default)
- docker-compose: Docker Compose container-based deployment
- systemd: systemd service-based deployment (future)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.protocols import BuildArtifact, Deployer, DeploymentContext
from hop3.plugins.deploy.uwsgi.deployer import UWSGIDeployer
from hop3.plugins.docker.deployer import DockerComposeDeployer

if TYPE_CHECKING:
    from hop3.orm import App


# Registry of deployment strategies
DEPLOYMENT_STRATEGIES: dict[str, type[Deployer]] = {
    "uwsgi": UWSGIDeployer,
    "docker-compose": DockerComposeDeployer,
    # Future runtimes:
    # "systemd": SystemdDeployer,
    # "podman": PodmanDeployer,
}


def get_deployment_strategy(app: App) -> Deployer:
    """Get the appropriate deployment strategy for an app based on its runtime.

    Args:
        app: The App instance to get the deployment strategy for

    Returns:
        An instance of the appropriate Deployer

    Raises:
        ValueError: If the app's runtime is not registered
    """
    runtime = app.runtime
    strategy_class = DEPLOYMENT_STRATEGIES.get(runtime)

    if not strategy_class:
        msg = f"Unknown runtime: {runtime}. Available runtimes: {list(DEPLOYMENT_STRATEGIES.keys())}"
        raise ValueError(msg)

    # Create a deployment context and dummy artifact for the strategy
    # This is a simplified approach - in practice, the context and artifact
    # would be passed from the deployment pipeline
    context = DeploymentContext(
        app_name=app.name,
        source_path=app.src_path,
        app_config={},
        app=app,
    )

    # Create a dummy artifact - for status checking we don't need real artifact info
    artifact = BuildArtifact(kind="virtualenv", location=str(app.virtualenv_path))

    return strategy_class(context=context, artifact=artifact)


def register_runtime(name: str, strategy_class: type[Deployer]) -> None:
    """Register a new deployment strategy.

    Args:
        name: The runtime name (e.g., "docker", "systemd")
        strategy_class: The Deployer class to register
    """
    DEPLOYMENT_STRATEGIES[name] = strategy_class


def list_runtimes() -> list[str]:
    """Get a list of all registered runtime names.

    Returns:
        List of runtime names
    """
    return list(DEPLOYMENT_STRATEGIES.keys())
