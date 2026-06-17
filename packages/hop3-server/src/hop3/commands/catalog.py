# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Catalog CLI/RPC commands (ADR 049)."""

from __future__ import annotations

from typing import ClassVar

from hop3.lib.registry import register
from hop3.server.catalog.refresh import refresh_catalog
from hop3.server.catalog.sync import CatalogSyncError
from hop3.server.catalog.verify import CatalogVerificationError

from ._base import Command
from ._response import error, text


@register
class CatalogRefreshCmd(Command):
    """Fetch and install the latest signed app catalog.

    Downloads the catalog tarball from the configured source, verifies its
    minisign signature against the key pinned in this build, checks it is not a
    rollback, and publishes it atomically. On any failure the previously
    published catalog is left untouched.

    Usage: hop3 catalog refresh
    """

    name: ClassVar[tuple[str, ...]] = ("catalog", "refresh")

    def call(self, *args, **kwargs) -> list:
        try:
            serial = refresh_catalog()
        except (CatalogSyncError, CatalogVerificationError) as e:
            return [error(f"Catalog refresh failed: {e}")]
        return [text(f"Catalog refreshed to serial {serial}.")]
