from typing import List, Type, cast

from hop3.core.hooks import hop3_hook_impl
from hop3.core.protocols import BuildStrategy, DeploymentStrategy

from .builder import DockerBuildStrategy
from .deployer import DockerComposeDeploymentStrategy


class DockerStrategiesPlugin:
    @hop3_hook_impl
    def get_build_strategies(self) -> List[Type[BuildStrategy]]:
        return cast(List[Type[BuildStrategy]], [DockerBuildStrategy])

    @hop3_hook_impl
    def get_deployment_strategies(self) -> List[Type[DeploymentStrategy]]:
        return cast(List[Type[DeploymentStrategy]], [DockerComposeDeploymentStrategy])
