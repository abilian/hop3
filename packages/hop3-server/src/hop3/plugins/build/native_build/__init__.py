# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Native build plugin - registers all native language builders."""

from __future__ import annotations

from hop3.builders import BUILDER_CLASSES
from hop3.core.hooks import hop3_hook_impl


class NativeBuildPlugin:
    """Plugin that provides native build strategies for various languages."""

    @hop3_hook_impl
    def get_builders(self) -> list:
        """Return all native builder classes."""
        return BUILDER_CLASSES


plugin = NativeBuildPlugin()
