# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Caddy proxy plugin for Hop3."""

from __future__ import annotations

from hop3.core.hooks import hookimpl

from ._setup import CaddyVirtualHost


class CaddyProxyPlugin:
    """Caddy reverse proxy plugin for Hop3."""

    name = "caddy"

    @hookimpl
    def get_proxies(self) -> list:
        """Return Caddy proxy strategy."""
        return [CaddyVirtualHost]


# Auto-register plugin instance when module is imported
plugin = CaddyProxyPlugin()
