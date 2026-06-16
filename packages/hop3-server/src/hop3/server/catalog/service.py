# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Catalog service for loading and caching app data."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .loader import load_apps
from .taxonomy import build_categories, build_tags

if TYPE_CHECKING:
    from .models import CatalogApp, Category, Tag

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


class CatalogService:
    """Singleton service for catalog data access.

    Loads apps from TOML files and caches them in memory.
    Thread-safe for read operations (no mutation after load).
    """

    _instance: CatalogService | None = None

    def __init__(self) -> None:
        self._apps: list[CatalogApp] = []
        self._categories: list[Category] = []
        self._tags: list[Tag] = []
        self._apps_by_id: dict[str, CatalogApp] = {}
        self._categories_by_id: dict[str, Category] = {}
        self._loaded: bool = False
        self._apps_dir: Path | None = None

    @classmethod
    def get_instance(cls) -> CatalogService:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def load(self, apps_dir: Path) -> None:
        """Load or reload catalog data from disk.

        Args:
            apps_dir: Directory containing app subdirectories with hop3.toml files
        """
        self._apps_dir = apps_dir
        self._apps = load_apps(apps_dir)
        self._categories = build_categories(self._apps)
        self._tags = build_tags(self._apps)

        # Build lookup dictionaries
        self._apps_by_id = {app.id: app for app in self._apps}
        self._categories_by_id = {cat.id: cat for cat in self._categories}

        self._loaded = True

    def ensure_loaded(self) -> None:
        """Ensure data is loaded, using default path if not."""
        if not self._loaded:
            # Default path: apps/catalog at repository root
            # Navigate from: hop3/server/catalog/service.py
            # to: apps/catalog/
            repo_root = Path(__file__).parent.parent.parent.parent.parent.parent.parent
            default_apps_dir = repo_root / "apps" / "catalog"
            if default_apps_dir.exists():
                self.load(default_apps_dir)
            else:
                # No apps available
                self._loaded = True

    @property
    def apps_dir(self) -> Path | None:
        """Get the apps directory path."""
        return self._apps_dir

    def get_app(self, app_id: str) -> CatalogApp | None:
        """Get an app by ID."""
        self.ensure_loaded()
        return self._apps_by_id.get(app_id)

    def list_apps(self) -> list[CatalogApp]:
        """Get all apps."""
        self.ensure_loaded()
        return self._apps

    def get_category(self, category_id: str) -> Category | None:
        """Get a category by ID."""
        self.ensure_loaded()
        return self._categories_by_id.get(category_id)

    def list_categories(self) -> list[Category]:
        """Get all categories."""
        self.ensure_loaded()
        return self._categories

    def list_tags(self) -> list[Tag]:
        """Get all tags."""
        self.ensure_loaded()
        return self._tags

    def get_featured_apps(self) -> list[CatalogApp]:
        """Get featured apps."""
        self.ensure_loaded()
        featured = []
        for app_id in FEATURED_APP_IDS:
            app = self._apps_by_id.get(app_id)
            if app:
                featured.append(app)
        return featured

    def search(self, query: str) -> list[CatalogApp]:
        """Search apps by title, description, or tags.

        Args:
            query: Search query string

        Returns:
            List of matching apps
        """
        self.ensure_loaded()
        query_lower = query.lower().strip()
        if not query_lower:
            return self._apps

        results = []
        for app in self._apps:
            if (
                query_lower in app.title.lower()
                or query_lower in app.description.lower()
                or any(query_lower in tag.lower() for tag in app.tags)
                or query_lower in app.author.lower()
            ):
                results.append(app)

        return results

    def get_apps_by_category(self, category_id: str) -> list[CatalogApp]:
        """Get all apps in a category."""
        category = self.get_category(category_id)
        if category:
            return category.apps
        return []
