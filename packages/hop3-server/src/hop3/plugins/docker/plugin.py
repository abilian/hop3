# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Docker plugin for Hop3.

This plugin provides Docker-based build and deployment strategies.
"""

from __future__ import annotations

from hop3.core.hooks import hop3_hook_impl
from hop3.core.protocols import BuildStrategy, DeploymentStrategy

from .builder import DockerBuildStrategy
from .deployer import DockerComposeDeploymentStrategy


class DockerPlugin:
    """Docker build and deployment plugin for Hop3.

    This plugin provides Docker-based build strategies and Docker Compose
    deployment strategies for applications.
    """

    name = "docker"

    @hop3_hook_impl
    def get_build_strategies(self) -> list[type[BuildStrategy]]:
        return [DockerBuildStrategy]

    @hop3_hook_impl
    def get_deployment_strategies(self) -> list[type[DeploymentStrategy]]:
        return [DockerComposeDeploymentStrategy]
