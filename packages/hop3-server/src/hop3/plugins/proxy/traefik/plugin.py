# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Traefik proxy plugin for Hop3."""

from __future__ import annotations

from hop3.core.hooks import hookimpl

from ._setup import TraefikVirtualHost


class TraefikProxyPlugin:
    """Traefik reverse proxy plugin for Hop3."""

    name = "traefik"

    @hookimpl
    def get_proxies(self) -> list:
        """Return Traefik proxy strategy."""
        return [TraefikVirtualHost]


# Auto-register plugin instance when module is imported
plugin = TraefikProxyPlugin()
