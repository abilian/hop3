from __future__ import annotations

from typing import cast

from hop3.core.hooks import hop3_hook_impl
from hop3.core.protocols import BuildStrategy, DeploymentStrategy

from .builder import DockerBuildStrategy
from .deployer import DockerComposeDeploymentStrategy


class DockerStrategiesPlugin:
    @hop3_hook_impl
    def get_build_strategies(self) -> list[type[BuildStrategy]]:
        return cast(list[type[BuildStrategy]], [DockerBuildStrategy])

    @hop3_hook_impl
    def get_deployment_strategies(self) -> list[type[DeploymentStrategy]]:
        return cast(list[type[DeploymentStrategy]], [DockerComposeDeploymentStrategy])
