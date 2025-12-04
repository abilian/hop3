# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Plugin to register LocalBuilder."""

from __future__ import annotations

from hop3.core.hooks import hop3_hook_impl

from .builder import LocalBuilder


class LocalBuildPlugin:
    """Plugin that provides local build capability."""

    name = "local-build"

    @hop3_hook_impl
    def get_builders(self) -> list:
        """Return LocalBuilder for building on the host."""
        return [LocalBuilder]


# Auto-register plugin instance when module is imported
plugin = LocalBuildPlugin()
