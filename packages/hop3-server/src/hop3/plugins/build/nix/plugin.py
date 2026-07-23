# Copyright (c) 2024-2025 Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Plugin registration for NixBuilder."""

from __future__ import annotations

from hop3.core.hooks import hop3_hook_impl

from .builder import NixBuilder


class NixBuildPlugin:
    """
    Plugin providing Nix build support.

    This plugin registers the NixBuilder, which handles applications
    with a hop3.nix file.
    """

    name = "nix-build"

    @hop3_hook_impl
    def get_builders(self) -> list:
        """Return NixBuilder for hop3.nix-based builds."""
        return [NixBuilder]


# Auto-register when module is imported
plugin = NixBuildPlugin()
