"""
Core and Docker plugins for Hop3 server.

(Stateless, registered at startup).
"""

from typing import List, Type, cast

from .core_strategies import BuildpackBuildStrategy, UWSGIDeploymentStrategy, DockerBuildStrategy, \
    DockerComposeDeploymentStrategy
from .hooks import hop3_hook_impl
from .protocols import BuildStrategy, DeploymentContext, BuildArtifact, DeploymentStrategy, DeploymentInfo


class CorePlugin:
    """The plugin container for Hop3's default strategies."""

    name = "core"

    @hop3_hook_impl
    def register_build_strategies(self) -> List[Type[BuildStrategy]]:
        # This hook returns the CLASS, not an instance.
        # `cast` tells mypy that this specific class list is compatible with the protocol list.
        return cast(List[Type[BuildStrategy]], [BuildpackBuildStrategy])

    @hop3_hook_impl
    def register_deployment_strategies(self) -> List[Type[DeploymentStrategy]]:
        return cast(List[Type[DeploymentStrategy]], [UWSGIDeploymentStrategy])


class DockerPlugin:
    """The plugin container for Docker-related strategies."""

    name = "docker"

    @hop3_hook_impl
    def register_build_strategies(self) -> List[Type[BuildStrategy]]:
        return cast(List[Type[BuildStrategy]], [DockerBuildStrategy])

    @hop3_hook_impl
    def register_deployment_strategies(self) -> List[Type[DeploymentStrategy]]:
        return cast(List[Type[DeploymentStrategy]], [DockerComposeDeploymentStrategy])
