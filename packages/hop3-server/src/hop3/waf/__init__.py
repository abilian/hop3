# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""WAF domain logic (ADR 050) — engine-agnostic, no plugin/DI wiring here."""

from __future__ import annotations

from pathlib import Path

from .compiler import (
    WafCompileError,
    compile_bans,
    compile_policy,
    compile_rules_file,
)

__all__ = [
    "WafCompileError",
    "compile_bans",
    "compile_policy",
    "compile_rules_file",
    "crs_dir",
]


def crs_dir() -> Path:
    """Filesystem path to the vendored OWASP CRS bundle (``hop3/waf/crs/``)."""
    return Path(__file__).parent / "crs"
