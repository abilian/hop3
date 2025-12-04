# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""LeWAF plugin registration for Hop3."""

from __future__ import annotations

from hop3.core.hooks import hookimpl

from .engine import LeWafEngine


class LeWafPlugin:
    """LeWAF Web Application Firewall plugin for Hop3.

    LeWAF is a pure Python WAF engine implementing SecLang (ModSecurity-compatible)
    with ~92% OWASP CRS compatibility.
    """

    name = "lewaf"

    @hookimpl
    def get_waf_engines(self) -> list:
        """Return LeWAF engine class."""
        return [LeWafEngine]


# Auto-register plugin instance when module is imported
plugin = LeWafPlugin()
