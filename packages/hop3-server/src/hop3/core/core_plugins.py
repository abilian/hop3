"""
Core and Docker plugins for Hop3 server.

(Stateless, registered at startup).
"""

from __future__ import annotations

from typing import cast

from .core_strategies import (
    BuildpackBuildStrategy,
    DockerBuildStrategy,
    DockerComposeDeploymentStrategy,
    UWSGIDeploymentStrategy,
)
from .hooks import hop3_hook_impl
from .protocols import (
    BuildStrategy,
    DeploymentStrategy,
)


class CorePlugin:
    """The plugin container for Hop3's default strategies."""

    name = "core"

    @hop3_hook_impl
    def register_build_strategies(self) -> list[type[BuildStrategy]]:
        # This hook returns the CLASS, not an instance.
        # `cast` tells mypy that this specific class list is compatible with the protocol list.
        return cast(list[type[BuildStrategy]], [BuildpackBuildStrategy])

    @hop3_hook_impl
    def register_deployment_strategies(self) -> list[type[DeploymentStrategy]]:
        return cast(list[type[DeploymentStrategy]], [UWSGIDeploymentStrategy])


class DockerPlugin:
    """The plugin container for Docker-related strategies."""

    name = "docker"

    @hop3_hook_impl
    def register_build_strategies(self) -> list[type[BuildStrategy]]:
        return cast(list[type[BuildStrategy]], [DockerBuildStrategy])

    @hop3_hook_impl
    def register_deployment_strategies(self) -> list[type[DeploymentStrategy]]:
        return cast(list[type[DeploymentStrategy]], [DockerComposeDeploymentStrategy])
