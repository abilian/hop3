# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Docker plugin for Hop3.

This plugin provides Docker-based build and deployment strategies.
"""

from __future__ import annotations

from hop3.core.hooks import hookimpl
from hop3.plugins.docker.builder import DockerBuilder
from hop3.plugins.docker.deployer import DockerComposeDeployer


class DockerPlugin:
    """Docker build and deployment plugin for Hop3.

    This plugin provides Docker-based build strategies and Docker Compose
    deployment strategies for applications.
    """

    name = "docker"

    @hookimpl
    def get_builders(self) -> list:
        """Return Docker build strategies.

        Returns:
            List containing DockerBuilder class
        """
        return [DockerBuilder]

    @hookimpl
    def get_deployers(self) -> list:
        """Return Docker Compose deployment strategies.

        Returns:
            List containing DockerComposeDeployer class
        """
        return [DockerComposeDeployer]


# Auto-register plugin instance when module is imported
plugin = DockerPlugin()
