# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test application catalog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class AppSource:
    """Represents a test application."""

    name: str
    path: Path
    category: str = ""
    description: str = ""

    @property
    def has_check_script(self) -> bool:
        """Check if app has a check.py script."""
        return (self.path / "check.py").exists()

    @property
    def has_procfile(self) -> bool:
        """Check if app has a Procfile."""
        return (self.path / "Procfile").exists()


class AppSourceCatalog:
    """Catalog of test applications.

    This class provides access to the test applications in the apps/test-apps directory.
    """

    def __init__(self, apps_dir: Path | None = None):
        """Initialize the catalog.

        Args:
            apps_dir: Path to test apps directory. If None, auto-detect from project structure.
        """
        if apps_dir is None:
            # Auto-detect: up from packages/hop3-testing to project root, then apps/test-apps
            # Path: .../hop3/packages/hop3-testing/src/hop3_testing/apps/catalog.py
            current_file = Path(__file__)
            # Go up: apps/ -> hop3_testing/ -> src/ -> hop3-testing/ -> packages/ -> hop3/
            project_root = current_file.parent.parent.parent.parent.parent.parent
            apps_dir = project_root / "apps" / "test-apps"

        self.apps_dir = apps_dir
        self._apps: dict[str, AppSource] | None = None

    def _scan_apps(self) -> dict[str, AppSource]:
        """Scan the apps directory for test applications.

        Returns:
            Dictionary mapping app names to TestApp objects
        """
        apps = {}

        if not self.apps_dir.exists():
            return apps

        for app_dir in sorted(self.apps_dir.iterdir()):
            # Skip non-directories and hidden files
            if not app_dir.is_dir() or app_dir.name.startswith("."):
                continue

            # Skip apps prefixed with "xxx-" (disabled apps)
            if app_dir.name.startswith("xxx-"):
                continue

            # Determine category from name prefix
            name = app_dir.name
            if name.startswith("000-"):
                category = "static"
            elif name.startswith("01"):
                category = "python-simple"
            elif name.startswith("02"):
                category = "nodejs"
            elif name.startswith("03"):
                category = "golang"
            elif name.startswith("04"):
                category = "ruby"
            elif name.startswith("1"):
                category = "python-advanced"
            else:
                category = "other"

            # Read description from README if available
            description = ""
            readme_path = app_dir / "README.md"
            if readme_path.exists():
                # Read first line as description
                with readme_path.open() as f:
                    first_line = f.readline().strip()
                    if first_line.startswith("#"):
                        description = first_line.lstrip("#").strip()

            apps[name] = AppSource(
                name=name,
                path=app_dir,
                category=category,
                description=description,
            )

        return apps

    @property
    def apps(self) -> dict[str, AppSource]:
        """Get all test applications.

        Returns:
            Dictionary mapping app names to TestApp objects
        """
        if self._apps is None:
            self._apps = self._scan_apps()
        return self._apps

    def get(self, name: str) -> AppSource | None:
        """Get a test application by name.

        Args:
            name: Application name

        Returns:
            TestApp object or None if not found
        """
        return self.apps.get(name)

    def filter(self, category: str | None = None, has_check: bool | None = None) -> Iterator[AppSource]:
        """Filter test applications.

        Args:
            category: Filter by category
            has_check: Filter by presence of check.py script

        Yields:
            TestApp objects matching the filters
        """
        for app in self.apps.values():
            if category is not None and app.category != category:
                continue

            if has_check is not None and app.has_check_script != has_check:
                continue

            yield app

    def list_categories(self) -> list[str]:
        """Get list of unique categories.

        Returns:
            List of category names
        """
        return sorted({app.category for app in self.apps.values()})

    def __iter__(self) -> Iterator[AppSource]:
        """Iterate over all test applications.

        Yields:
            TestApp objects
        """
        yield from self.apps.values()

    def __len__(self) -> int:
        """Get number of test applications.

        Returns:
            Number of apps
        """
        return len(self.apps)
