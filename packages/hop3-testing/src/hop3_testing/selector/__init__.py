# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test selection logic for hop3-testing.

This module provides:
- Selector: Selects tests based on mode and filters
- Mode configurations for dev, ci, nightly, release, package
"""

from __future__ import annotations

from .modes import ModeConfig, get_mode_config
from .selector import Selector

__all__ = [
    "ModeConfig",
    "Selector",
    "get_mode_config",
]
