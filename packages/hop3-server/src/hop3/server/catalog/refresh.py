# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Catalog refresh orchestration (ADR 049): fetch → verify+publish → reload.

Ties together the pieces that individually live in ``sync.py`` (fetch, verify,
atomic publish) and ``service.py`` (in-memory reload), reading the source URL and
the pinned key from configuration. The signature lives at ``<url>.minisig``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hop3.config import config

from .keys import get_catalog_public_key
from .service import CatalogService
from .sync import (
    CatalogInstallResult,
    CatalogSyncError,
    fetch_to,
    install_catalog_tarball,
)

_SIG_SUFFIX = ".minisig"


def refresh_catalog(
    *,
    source_url: str | None = None,
    public_key: str | None = None,
    catalog_root: Path | None = None,
    state_root: Path | None = None,
) -> CatalogInstallResult:
    """
    Fetch, verify, publish, and load the latest catalog.

    Returns the serial and whether anything changed — a source still offering
    the installed serial is a no-op, not a failure. Raises ``CatalogSyncError``
    / ``CatalogVerificationError`` on any real failure, leaving the currently
    published catalog untouched. Arguments default to the configured values;
    they exist mainly for testing.
    """
    url = source_url or config.CATALOG_SOURCE_URL
    key = public_key if public_key is not None else get_catalog_public_key()
    if not key.strip():
        msg = (
            "No catalog signing public key is compiled into this build; refusing "
            "to fetch an unverifiable catalog (see hop3.server.catalog.keys)."
        )
        raise CatalogSyncError(msg)

    catalog_root = catalog_root or config.CATALOG_ROOT
    state_root = state_root or config.CATALOG_STATE_ROOT

    with tempfile.TemporaryDirectory(prefix="hop3-catalog-fetch-") as tmp:
        tarball = Path(tmp) / "catalog.tar.gz"
        sigfile = Path(tmp) / ("catalog.tar.gz" + _SIG_SUFFIX)
        fetch_to(url, tarball)
        fetch_to(url + _SIG_SUFFIX, sigfile)
        result = install_catalog_tarball(
            tarball, sigfile.read_text(), key, catalog_root, state_root
        )

    CatalogService.get_instance().reload()
    return result
