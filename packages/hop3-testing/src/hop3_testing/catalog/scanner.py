# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test catalog scanner.

Discovers test.toml files and legacy test apps to build a unified catalog.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from .loader import (
    TestDefinitionError,
    generate_test_definition_from_app,
    load_test_definition,
)
from .models import Category, Priority, TargetType, TestDefinition, Tier

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)


class Catalog:
    """Discovers and indexes all tests in the project.

    The catalog scans multiple locations for tests:
    - apps/test-apps/: Deployment test applications
    - demos/: Demo scripts and applications
    - docs/src/tutorials/: Tutorial markdown files

    Tests should be defined via test.toml files with explicit categories.
    Legacy apps without test.toml can still be loaded with default settings.
    """

    # Default scan paths relative to project root
    DEFAULT_SCAN_PATHS: ClassVar[list[str]] = [
        "apps/test-apps",
        "demos",
        "docs/src/tutorials",
    ]

    def __init__(self, root: Path | None = None):
        """Initialize the catalog.

        Args:
            root: Project root directory. If None, auto-detect.
        """
        if root is None:
            root = self._find_project_root()
        self.root = root
        self._tests: dict[str, TestDefinition] = {}
        self._by_category: dict[str, list[TestDefinition]] = {}
        self._by_tier: dict[str, list[TestDefinition]] = {}
        self._by_priority: dict[str, list[TestDefinition]] = {}
        self._errors: list[tuple[Path, str]] = []

    def _find_project_root(self) -> Path:
        """Find project root by looking for pyproject.toml."""
        # Start from current file and go up
        current = Path(__file__).parent
        for _ in range(10):  # Max 10 levels up
            if (current / "pyproject.toml").exists():
                return current
            parent = current.parent
            if parent == current:
                break
            current = parent

        # Fallback to current working directory
        return Path.cwd()

    def scan(self, paths: list[str] | None = None) -> None:
        """Scan directories for test definitions.

        Args:
            paths: Paths to scan (relative to root). If None, use defaults.
        """
        scan_paths = paths or self.DEFAULT_SCAN_PATHS
        self._tests.clear()
        self._errors.clear()

        for rel_path in scan_paths:
            full_path = self.root / rel_path
            if not full_path.exists():
                logger.debug("Scan path does not exist: %s", full_path)
                continue

            self._scan_directory(full_path, rel_path)

        self._build_indexes()
        logger.info(
            "Catalog loaded: %d tests, %d errors", len(self._tests), len(self._errors)
        )

    def _scan_directory(self, path: Path, rel_path: str) -> None:
        """Scan a single directory for tests."""
        # Check for test.toml files recursively
        for test_toml in path.rglob("test.toml"):
            self._load_test_from_toml(test_toml)

        # Also scan for legacy apps (directories with Procfile but no test.toml)
        for item in path.iterdir():
            if not item.is_dir():
                continue

            # Skip hidden and disabled directories
            if item.name.startswith(".") or item.name.startswith("xxx-"):
                continue

            # Skip if already has test.toml
            if (item / "test.toml").exists():
                continue

            # Check if it looks like a test app
            if self._is_legacy_app(item):
                self._load_legacy_app(item, rel_path)

    def _is_legacy_app(self, path: Path) -> bool:
        """Check if a directory looks like a legacy test app."""
        # Must have Procfile or be a static site
        if (path / "Procfile").exists():
            return True
        if (path / "index.html").exists():
            return True
        # Common demo structure
        return (path / "app").is_dir()

    def _load_test_from_toml(self, path: Path) -> None:
        """Load a test from a test.toml file."""
        try:
            test_def = load_test_definition(path)
            self._add_test(test_def)
        except TestDefinitionError as e:
            logger.warning("Failed to load %s: %s", path, e)
            self._errors.append((path, str(e)))

    def _load_legacy_app(self, path: Path, rel_path: str) -> None:
        """Load a legacy app without test.toml.

        Legacy apps are loaded with default category settings.
        For proper categorization, add a test.toml file.
        """
        try:
            test_def = generate_test_definition_from_app(path)
            self._add_test(test_def)
        except Exception as e:
            logger.warning("Failed to load legacy app %s: %s", path, e)
            self._errors.append((path, str(e)))

    def _add_test(self, test_def: TestDefinition) -> None:
        """Add a test to the catalog."""
        if test_def.name in self._tests:
            existing = self._tests[test_def.name]
            logger.warning(
                "Duplicate test name: %s (existing: %s, new: %s)",
                test_def.name,
                existing.source_path,
                test_def.source_path,
            )
            # Keep the one with test.toml if there's a conflict
            if test_def.source_path and test_def.source_path.name == "test.toml":
                self._tests[test_def.name] = test_def
        else:
            self._tests[test_def.name] = test_def

    def _build_indexes(self) -> None:
        """Build category, tier, and priority indexes."""
        self._by_category = {}
        self._by_tier = {}
        self._by_priority = {}

        for test in self._tests.values():
            # Index by category
            cat = test.category.value
            if cat not in self._by_category:
                self._by_category[cat] = []
            self._by_category[cat].append(test)

            # Index by tier
            tier = test.tier.value
            if tier not in self._by_tier:
                self._by_tier[tier] = []
            self._by_tier[tier].append(test)

            # Index by priority
            prio = test.priority.value
            if prio not in self._by_priority:
                self._by_priority[prio] = []
            self._by_priority[prio].append(test)

    def all_tests(self) -> list[TestDefinition]:
        """Return all discovered tests."""
        return list(self._tests.values())

    def get_test(self, name: str) -> TestDefinition | None:
        """Get a specific test by name."""
        return self._tests.get(name)

    def by_category(self, category: str | Category) -> list[TestDefinition]:
        """Get tests by category."""
        if isinstance(category, Category):
            category = category.value
        return self._by_category.get(category, [])

    def by_tier(self, tier: str | Tier) -> list[TestDefinition]:
        """Get tests by tier."""
        if isinstance(tier, Tier):
            tier = tier.value
        return self._by_tier.get(tier, [])

    def by_priority(self, priority: str | Priority) -> list[TestDefinition]:
        """Get tests by priority."""
        if isinstance(priority, Priority):
            priority = priority.value
        return self._by_priority.get(priority, [])

    def filter(
        self,
        categories: list[str] | None = None,
        tiers: list[str] | None = None,
        priorities: list[str] | None = None,
        targets: list[str] | None = None,
        tags: list[str] | None = None,
        name_pattern: str | None = None,
    ) -> list[TestDefinition]:
        """Filter tests by multiple criteria.

        Args:
            categories: Filter by category (deployment, demo, tutorial)
            tiers: Filter by tier (fast, medium, slow, very-slow)
            priorities: Filter by priority (P0, P1, P2)
            targets: Filter by supported target type (docker, remote, local)
            tags: Filter by metadata.covers tags
            name_pattern: Filter by name pattern (substring match)

        Returns:
            List of matching tests, sorted by priority then tier then name
        """
        result = []

        for test in self._tests.values():
            # Category filter
            if categories and test.category.value not in categories:
                continue

            # Tier filter
            if tiers and test.tier.value not in tiers:
                continue

            # Priority filter
            if priorities and test.priority.value not in priorities:
                continue

            # Target filter
            if targets:
                target_types = [TargetType(t) for t in targets]
                if not any(test.can_run_on(t) for t in target_types):
                    continue

            # Tags filter
            if tags:
                if not any(tag in test.metadata.covers for tag in tags):
                    continue

            # Name pattern filter
            if name_pattern and name_pattern.lower() not in test.name.lower():
                continue

            result.append(test)

        # Sort by priority, then tier, then name
        priority_order = {"P0": 0, "P1": 1, "P2": 2}
        tier_order = {"fast": 0, "medium": 1, "slow": 2, "very-slow": 3}

        result.sort(
            key=lambda t: (
                priority_order.get(t.priority.value, 99),
                tier_order.get(t.tier.value, 99),
                t.name,
            )
        )

        return result

    def categories(self) -> list[str]:
        """Get list of unique categories."""
        return sorted(self._by_category.keys())

    def tiers(self) -> list[str]:
        """Get list of unique tiers."""
        return sorted(self._by_tier.keys())

    def priorities(self) -> list[str]:
        """Get list of unique priorities."""
        return sorted(self._by_priority.keys())

    def errors(self) -> list[tuple[Path, str]]:
        """Get list of loading errors."""
        return list(self._errors)

    def __iter__(self) -> Iterator[TestDefinition]:
        """Iterate over all tests."""
        yield from self._tests.values()

    def __len__(self) -> int:
        """Get number of tests."""
        return len(self._tests)

    def __contains__(self, name: str) -> bool:
        """Check if test exists by name."""
        return name in self._tests
