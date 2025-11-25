# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Plugin to register static deployment strategy."""

from __future__ import annotations

from hop3.core.hooks import hop3_hook_impl

from .deployer import StaticDeployer


class StaticDeployPlugin:
    """Plugin that provides static file deployment strategy."""

    name = "static-deploy"

    @hop3_hook_impl
    def get_deployers(self) -> list:
        """Return static deployment strategy."""
        return [StaticDeployer]


# Auto-register plugin instance when module is imported
plugin = StaticDeployPlugin()
