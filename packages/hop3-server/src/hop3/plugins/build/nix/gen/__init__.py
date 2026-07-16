# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Template-based hop3.nix generator.

Generates Nix expressions from declarative AppSpec specifications,
implementing ADR 008 (Template-Based Nix Expression Generation).

Usage:
    from hop3.plugins.build.nix.gen import generate, AppSpec, Source
    spec = AppSpec(pname="myapp", version="1.0", ...)
    nix_text = generate(spec)
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.registry import generate
from hop3.plugins.build.nix.gen.spec import (
    AppSpec,
    ConditionalEnvVar,
    ConfigFile,
    FileMapping,
    Source,
)

__all__ = [
    "AppSpec",
    "ConditionalEnvVar",
    "ConfigFile",
    "FileMapping",
    "Source",
    "generate",
]
