# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Plugin to register uWSGI deployment strategy."""

from __future__ import annotations

from hop3.core.hooks import hop3_hook_impl

from .deployer import UWSGIDeployer


class UWSGIPlugin:
    """Plugin that provides uWSGI deployment strategy."""

    name = "uwsgi-deploy"

    @hop3_hook_impl
    def get_deployers(self) -> list:
        """Return uWSGI deployment strategy."""
        return [UWSGIDeployer]


# Auto-register plugin instance when module is imported
plugin = UWSGIPlugin()
