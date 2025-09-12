# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from hop3.core.hooks import hop3_hook_impl
from hop3.core.protocols import BuildStrategy, DeploymentStrategy

from .builder import DockerBuildStrategy
from .deployer import DockerComposeDeploymentStrategy


class DockerPlugin:
    @hop3_hook_impl
    def get_build_strategies(self) -> list[type[BuildStrategy]]:
        return [DockerBuildStrategy]

    @hop3_hook_impl
    def get_deployment_strategies(self) -> list[type[DeploymentStrategy]]:
        return [DockerComposeDeploymentStrategy]
