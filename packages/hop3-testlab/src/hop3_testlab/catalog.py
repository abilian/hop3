# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Cached catalog access for the Test Lab web process.

The web process needs the test catalog for two read-only things the result DB
doesn't carry:

- **Per-profile counts** for the mode dropdown ("(N)").
- **Human titles** (``TestDefinition.description``) so runs show "Demo 1: uWSGI
  Deployment" instead of the path leaf "demo01".

Scanning the apps/ tree costs ~1-2 s, so the catalog is built once and cached for
the process lifetime (tests don't change at runtime). Mode counts and titles are
derived per call from the cached catalog, so profile edits (which change the
overrides file) are reflected without a rescan.
"""

from __future__ import annotations

import fnmatch
import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from hop3_testing.catalog import Catalog, default_scan_paths
from hop3_testing.targets.helpers import find_project_root

from hop3_testlab.discriminators import short_app

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def build_catalog(root: Path) -> Catalog:
    """Scan ``root``'s app tree into a fresh catalog (uncached).

    Used for both the local repo (cached via :func:`get_catalog`) and a fetched
    source workspace (``source@ref``), which the worker scans to resolve a run's
    app selector (v2 spec §A/§5). Scan set comes from the engine's shared
    ``default_scan_paths`` — one source of truth, no Lab-local copy to drift.
    """
    catalog = Catalog(root)
    catalog.scan(paths=default_scan_paths(root))
    return catalog


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    """The local repo's catalog, cached for the process lifetime. ~1-2 s first call."""
    return build_catalog(find_project_root())


def resolve_selector(root: Path, pattern: str) -> list[str]:
    """Catalog test names under ``root`` matching the literal glob ``pattern``.

    Matched against catalog **names** (repo-relative app paths) so only real test
    apps are selected, never a stray file. The caller passes ``pattern`` as a
    literal string (quoted on the CLI); we expand it here — server-side, against
    the workspace — never the local shell against the caller's disk (v2 spec §1).
    """
    names = [t.name for t in build_catalog(root)]
    # ponytail: fnmatch '*' spans '/', which is fine for the flat apps/<dir> layout.
    return sorted(n for n in names if fnmatch.fnmatchcase(n, pattern))


def _safe_catalog() -> Catalog | None:
    """The cached catalog, or None if scanning isn't possible (degrade, don't crash).

    A headless/packaged deploy may not have the apps/ tree; the dropdown and run
    views must still render (counts omitted, titles fall back to the path leaf).
    """
    try:
        return get_catalog()
    except Exception as e:  # any scan failure degrades gracefully
        logger.warning("Test Lab catalog unavailable: %s", e)
        return None


def title_map() -> dict[str, str]:
    """Map catalog test name → human title (its description, else the path leaf)."""
    catalog = _safe_catalog()
    if catalog is None:
        return {}
    return {t.name: (t.description or short_app(t.name)) for t in catalog}
