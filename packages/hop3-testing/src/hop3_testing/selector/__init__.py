# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test selection logic for hop3-testing.

This module provides:
- Selector: Selects tests based on mode and filters
- Mode configurations: smoke, ci, curated, tag-coverage, combo-coverage, broad, full
"""

from __future__ import annotations

from .modes import (
    BUILTIN_MODE_NAMES,
    VALID_PRIORITIES,
    VALID_TARGETS,
    VALID_TIERS,
    ModeConfig,
    customized_mode_names,
    delete_mode,
    get_mode_config,
    list_modes,
    load_modes,
    reset_mode,
    save_mode,
)
from .selector import Selector

__all__ = [
    "BUILTIN_MODE_NAMES",
    "VALID_PRIORITIES",
    "VALID_TARGETS",
    "VALID_TIERS",
    "ModeConfig",
    "Selector",
    "customized_mode_names",
    "delete_mode",
    "get_mode_config",
    "list_modes",
    "load_modes",
    "reset_mode",
    "save_mode",
]
