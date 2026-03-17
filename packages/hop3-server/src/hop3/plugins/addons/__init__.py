# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared utilities for addon plugins."""

from __future__ import annotations

from .cli import display_credentials
from .secrets import (
    delete_addon_secrets,
    load_addon_secrets,
    save_addon_secrets,
)

__all__ = [
    "delete_addon_secrets",
    "display_credentials",
    "load_addon_secrets",
    "save_addon_secrets",
]
