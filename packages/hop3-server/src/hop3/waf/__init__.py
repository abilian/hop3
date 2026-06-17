# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""WAF domain logic (ADR 048) — engine-agnostic, no plugin/DI wiring here."""

from __future__ import annotations

from .compiler import WafCompileError, compile_policy

__all__ = ["WafCompileError", "compile_policy"]
