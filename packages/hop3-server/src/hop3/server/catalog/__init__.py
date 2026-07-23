# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Hop3 Catalog module.

Provides app catalog browsing and installation functionality.
"""

from __future__ import annotations

from .models import CatalogApp, Category, Tag
from .service import CatalogService

__all__ = [
    "CatalogApp",
    "CatalogService",
    "Category",
    "Tag",
]
