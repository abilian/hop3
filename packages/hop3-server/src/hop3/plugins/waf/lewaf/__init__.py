# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""LeWAF plugin for Hop3.

LeWAF is a pure Python WAF implementing SecLang (ModSecurity-compatible)
with ~92% OWASP CRS compatibility.

Usage:
    from hop3.plugins.waf.lewaf import LeWafEngine, is_lewaf_available

    if is_lewaf_available():
        engine = LeWafEngine()
        engine.configure_app(waf_config)
"""

from __future__ import annotations

from .engine import LeWafEngine, is_lewaf_available

__all__ = ["LeWafEngine", "is_lewaf_available"]
