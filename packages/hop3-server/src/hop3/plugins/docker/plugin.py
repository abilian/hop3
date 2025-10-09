# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Docker plugin for Hop3.

This plugin provides Docker-based build and deployment strategies.
"""

from __future__ import annotations

from hop3.core.hooks import hookimpl


class DockerPlugin:
    """Docker build and deployment plugin for Hop3.

    This plugin provides Docker-based build strategies and Docker Compose
    deployment strategies for applications.
    """

    name = "docker"

    @hookimpl
    def get_build_strategies(self) -> list:
        # TODO: Implement Docker build strategies
        return []

    @hookimpl
    def get_deployment_strategies(self) -> list:
        # TODO: Implement Docker Compose deployment strategies
        return []


# Auto-register plugin instance when module is imported
plugin = DockerPlugin()
