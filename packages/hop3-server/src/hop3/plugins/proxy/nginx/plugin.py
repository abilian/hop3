# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Nginx proxy plugin for Hop3."""

from __future__ import annotations

from hop3.core.hooks import hookimpl

from ._setup import NginxVirtualHost


class NginxProxyPlugin:
    """Nginx reverse proxy plugin for Hop3."""

    name = "nginx"

    @hookimpl
    def get_proxies(self) -> list:
        """Return Nginx proxy strategy."""
        return [NginxVirtualHost]


# Auto-register plugin instance when module is imported
plugin = NginxProxyPlugin()
