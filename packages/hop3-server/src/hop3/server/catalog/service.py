# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Catalog service: in-memory access to the verified, on-disk catalog (ADR 049).

The service loads the catalog that ``sync.py`` has already fetched, verified, and
published to ``config.CATALOG_ROOT``. It does not fetch or re-verify; it reads the
published tree, driving off the signed ``index.json`` so only indexed apps are ever
surfaced (ADR 049 F1).

Reads are lock-free against an immutable snapshot; a load/reload builds a fresh
snapshot off to the side and swaps the single reference under a lock, so a concurrent
request always sees either the old or the new complete catalog, never a half-built
one (ADR 049 F2).
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hop3.config import config

from .loader import load_apps, load_apps_from_index
from .taxonomy import build_categories, build_tags

if TYPE_CHECKING:
    from pathlib import Path

    from .models import CatalogApp, Category, Tag

logger = logging.getLogger(__name__)

_INDEX_FILENAME = "index.json"

# Featured apps (curated list)
FEATURED_APP_IDS = [
    "nextcloud",
    "moodle",
    "peertube",
    "rocketchat",
    "matomo",
    "openproject",
    "baserow",
    "taiga",
    "calcom",
    "redmine",
    "hedgedoc",
    "umami",
]


@dataclass(frozen=True)
class _Snapshot:
    """An immutable, atomically-swappable view of the loaded catalog."""

    available: bool
    apps_dir: Path | None
    apps: list[CatalogApp] = field(default_factory=list)
    categories: list[Category] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    apps_by_id: dict[str, CatalogApp] = field(default_factory=dict)
    categories_by_id: dict[str, Category] = field(default_factory=dict)


_UNAVAILABLE = _Snapshot(available=False, apps_dir=None)


def _default_catalog_dir() -> Path:
    """The published catalog directory (a symlink managed by sync)."""
    return config.CATALOG_ROOT


class CatalogService:
    """Singleton access to the published catalog. Thread-safe."""

    _instance: CatalogService | None = None

    def __init__(self) -> None:
        self._snapshot: _Snapshot | None = None
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> CatalogService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def load(self, apps_dir: Path) -> None:
        """Load from a specific directory and atomically swap it in."""
        self._swap(self._build(apps_dir, available=True))

    def reload(self) -> None:
        """Re-resolve from config and atomically swap (call after a sync)."""
        self._swap(self._resolve())

    def is_available(self) -> bool:
        """Whether a catalog has actually been synced/loaded."""
        return self._current().available

    @property
    def apps_dir(self) -> Path | None:
        return self._current().apps_dir

    def get_app(self, app_id: str) -> CatalogApp | None:
        return self._current().apps_by_id.get(app_id)

    def list_apps(self) -> list[CatalogApp]:
        return self._current().apps

    def get_category(self, category_id: str) -> Category | None:
        return self._current().categories_by_id.get(category_id)

    def list_categories(self) -> list[Category]:
        return self._current().categories

    def list_tags(self) -> list[Tag]:
        return self._current().tags

    def get_featured_apps(self) -> list[CatalogApp]:
        snap = self._current()
        return [snap.apps_by_id[i] for i in FEATURED_APP_IDS if i in snap.apps_by_id]

    def search(self, query: str) -> list[CatalogApp]:
        """Search apps by title, description, tags, or author."""
        snap = self._current()
        q = query.lower().strip()
        if not q:
            return snap.apps
        return [
            app
            for app in snap.apps
            if q in app.title.lower()
            or q in app.description.lower()
            or any(q in tag.lower() for tag in app.tags)
            or q in app.author.lower()
        ]

    def get_apps_by_category(self, category_id: str) -> list[CatalogApp]:
        category = self.get_category(category_id)
        return category.apps if category else []

    # --- internals -----------------------------------------------------------

    def _current(self) -> _Snapshot:
        """Return the live snapshot, building it on first access."""
        snap = self._snapshot
        if snap is not None:
            return snap
        with self._lock:
            if self._snapshot is None:
                self._snapshot = self._resolve()
            return self._snapshot

    def _swap(self, snapshot: _Snapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def _resolve(self) -> _Snapshot:
        """Build a snapshot from the configured catalog dir, or mark unavailable."""
        catalog_dir = _default_catalog_dir()
        if catalog_dir.exists():
            return self._build(catalog_dir, available=True)
        # Not an error (a fresh node has no catalog yet) but it must be visible:
        # log loudly and report unavailable rather than serving an empty catalog as
        # if it were a successful "0 apps" result (ADR 049 / CLAUDE.md fail-loud).
        logger.warning(
            "Catalog not available at %s — run a catalog sync to populate it.",
            catalog_dir,
        )
        return _UNAVAILABLE

    def _build(self, apps_dir: Path, *, available: bool) -> _Snapshot:
        apps = self._load_apps(apps_dir)
        categories = build_categories(apps)
        tags = build_tags(apps)
        return _Snapshot(
            available=available,
            apps_dir=apps_dir,
            apps=apps,
            categories=categories,
            tags=tags,
            apps_by_id={app.id: app for app in apps},
            categories_by_id={cat.id: cat for cat in categories},
        )

    def _load_apps(self, apps_dir: Path) -> list[CatalogApp]:
        index_path = apps_dir / _INDEX_FILENAME
        if index_path.exists():
            index = json.loads(index_path.read_text())
            return load_apps_from_index(apps_dir, index)
        # No index → unsigned local/dev directory; scan it directly.
        return load_apps(apps_dir)
