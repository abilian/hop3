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

import logging
from functools import lru_cache
from operator import itemgetter
from typing import TYPE_CHECKING

from hop3_testing.catalog import Catalog
from hop3_testing.selector.modes import get_mode_config, list_modes
from hop3_testing.selector.selector import Selector
from hop3_testing.targets.helpers import find_project_root

from hop3_testlab.discriminators import short_app, type_of, variant_of

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_testing.catalog.models import TestDefinition

logger = logging.getLogger(__name__)

# Languages a test may exercise — used to derive the picker's language tag from
# a test's metadata when it isn't stated explicitly.
_LANGUAGES = frozenset({
    "python",
    "php",
    "node",
    "nodejs",
    "go",
    "golang",
    "ruby",
    "java",
    "rust",
    "elixir",
    "clojure",
    "dotnet",
    "static",
})


def _language_of(test: TestDefinition) -> str:
    """Primary language/toolchain of a test, or "" if not discernible."""
    if test.metadata.language:
        return test.metadata.language.lower()
    for tag in test.metadata.covers:
        if tag.lower() in _LANGUAGES:
            return tag.lower()
    return ""


def _scan_paths(root: Path) -> list[str]:
    """Default scan set: every apps/ subdir, demos, and the tutorial source.

    Mirrors ``hop3_testing.cli.commands.test._get_default_scan_paths`` (source
    tutorials, not the rendered tree, which has the executable markers stripped).
    """
    paths: list[str] = []
    apps = root / "apps"
    if apps.is_dir():
        paths += [
            str(c.relative_to(root)) for c in sorted(apps.iterdir()) if c.is_dir()
        ]
    if (root / "demos").is_dir():
        paths.append("demos")
    if (root / "docs/tutorials").is_dir():
        paths.append("docs/tutorials")
    elif (root / "docs/src/tutorials").is_dir():
        paths.append("docs/src/tutorials")
    return paths


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    """Build and cache the catalog (process-lifetime). ~1-2 s on first call."""
    root = find_project_root()
    catalog = Catalog(root)
    catalog.scan(paths=_scan_paths(root))
    return catalog


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


def mode_counts() -> dict[str, int]:
    """Number of tests each mode selects (handles set-cover and explicit lists)."""
    catalog = _safe_catalog()
    if catalog is None:
        return {}
    selector = Selector(catalog)
    counts: dict[str, int] = {}
    for name in list_modes():
        try:
            counts[name] = len(selector.select(get_mode_config(name)))
        except Exception as e:  # one bad mode shouldn't blank the rest
            logger.warning("Count for mode %r failed: %s", name, e)
    return counts


def title_map() -> dict[str, str]:
    """Map catalog test name → human title (its description, else the path leaf)."""
    catalog = _safe_catalog()
    if catalog is None:
        return {}
    return {t.name: (t.description or short_app(t.name)) for t in catalog}


def valid_test_names() -> set[str]:
    """Set of catalog test names, for validating a curated profile's picks."""
    catalog = _safe_catalog()
    return {t.name for t in catalog} if catalog else set()


def tests_grouped() -> list[dict[str, str]]:
    """All tests with display fields for the profile picker, ordered for grouping."""
    catalog = _safe_catalog()
    if catalog is None:
        return []
    rows = [
        {
            "name": t.name,
            "title": t.description or short_app(t.name),
            "type": type_of(t.name),
            "variant": variant_of(t.name),
            "language": _language_of(t) or "",
        }
        for t in catalog
    ]
    rows.sort(key=itemgetter("type", "variant", "name"))
    return rows
