# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""LeWAF WAF-engine plugin registration (ADR 048)."""

from __future__ import annotations

from hop3.core.hooks import hookimpl

from .engine import LeWafEngine


class LeWafPlugin:
    """Registers the LeWAF Layer-7 WAF engine."""

    name = "lewaf"

    @hookimpl
    def get_waf_engines(self) -> list:
        """Return the LeWAF engine class."""
        return [LeWafEngine]


# Auto-register plugin instance when module is imported (see core/plugins.py).
plugin = LeWafPlugin()
