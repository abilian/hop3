# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test catalog scanner.

Discovers test.toml files and hop3.toml-based test apps to build a unified catalog.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .loader import (
    TestDefinitionError,
    generate_test_definition_from_app,
    generate_tutorial_test_definition,
    load_test_definition_smart,
)
from .models import TargetType, TestDefinition, Tier

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

IGNORE_FILE = "HOP3_TEST_IGNORE"

# Executable validoc fences (same set the tutorial runner counts). A tutorial
# markdown with none of these runs no commands — it's documentation, not a test.
_VALIDOC_BLOCK_RE = re.compile(r"^```(?:bash\s+exec|output|file)\b", re.MULTILINE)


def _has_executable_blocks(md_path: Path) -> bool:
    """True if a tutorial markdown has at least one executable validoc block."""
    try:
        return bool(_VALIDOC_BLOCK_RE.search(md_path.read_text(encoding="utf-8")))
    except OSError:
        return False


class Catalog:
    """Discovers and indexes all tests in the project.

    The catalog discovers test apps by scanning explicitly provided paths.
    Any subdirectory containing hop3.toml or test.toml files is included.
    Directories containing a HOP3_TEST_IGNORE file are excluded.
    """

    def __init__(self, root: Path | None = None):
        """Initialize the catalog.

        Args:
            root: Project root directory. If None, auto-detect.
        """
        if root is None:
            root = self._find_project_root()
        self.root = root
        self._tests: dict[str, TestDefinition] = {}
        self._by_path: dict[Path, TestDefinition] = {}  # Index by app directory path
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
            paths: Explicit paths to scan (relative to root). Required.

        Raises:
            ValueError: If paths is None or empty.
        """
        if not paths:
            msg = "scan() requires explicit paths to scan"
            raise ValueError(msg)

        self._tests.clear()
        self._errors.clear()

        scan_targets = []
        for rel_path in paths:
            full_path = self.root / rel_path
            if full_path.exists():
                scan_targets.append((full_path, rel_path))
            else:
                logger.debug("Scan path does not exist: %s", full_path)

        for full_path, rel_path in scan_targets:
            self._scan_directory(full_path, rel_path)

        self._build_indexes()
        logger.info(
            "Catalog loaded: %d tests, %d errors", len(self._tests), len(self._errors)
        )

    def _find_demo_internal_dirs(self, path: Path, rel_path: str) -> set[Path]:
        """Find subdirectories that are internal to demo directories.

        For demos/, demo directories often contain app/ subdirectories with
        hop3.toml files. These should NOT be treated as separate tests.

        Args:
            path: Directory to scan
            rel_path: Relative path for context

        Returns:
            Set of paths that are internal to demos (should be skipped)
        """
        demo_internal_dirs: set[Path] = set()
        is_demos_dir = "demos" in rel_path or rel_path == "demos"

        if not is_demos_dir:
            return demo_internal_dirs

        # Find all demo directories and their subdirectories
        for item in path.iterdir():
            if item.is_dir() and (item / "demo-script.py").exists():
                # This is a demo directory - mark all its subdirs as internal
                for subdir in item.rglob("*"):
                    if subdir.is_dir():
                        demo_internal_dirs.add(subdir)

        return demo_internal_dirs

    def _has_ignore_ancestor(self, path: Path, root: Path) -> bool:
        """Check if any ancestor of path (up to root) contains HOP3_TEST_IGNORE."""
        current = path.parent
        while current not in {root, current.parent}:
            if (current / IGNORE_FILE).exists():
                return True
            current = current.parent
        return False

    def _scan_directory(self, path: Path, rel_path: str) -> None:  # noqa: C901
        """Scan a single directory for tests.

        Scans for:
        1. test.toml files (explicit test definitions)
        2. hop3.toml files (app definitions that can be used for testing)

        Directories containing a HOP3_TEST_IGNORE file are skipped entirely.
        """
        # Skip directory if it has an ignore marker
        if (path / IGNORE_FILE).exists():
            logger.debug("Skipping ignored directory: %s", path)
            return

        processed_dirs: set[Path] = set()
        demo_internal_dirs = self._find_demo_internal_dirs(path, rel_path)

        # Check for test.toml files recursively (sorted for deterministic order)
        for test_toml in sorted(path.rglob("test.toml")):
            app_dir = test_toml.parent
            if self._has_ignore_ancestor(app_dir, path):
                continue
            if app_dir not in processed_dirs and app_dir not in demo_internal_dirs:
                self._load_test_smart(app_dir)
                processed_dirs.add(app_dir)

        # Check for hop3.toml files recursively (that don't have test.toml)
        for hop3_toml in sorted(path.rglob("hop3.toml")):
            app_dir = hop3_toml.parent
            if self._has_ignore_ancestor(app_dir, path):
                continue
            # Skip internal demo subdirectories (e.g., demos/demoNN/app/)
            if app_dir in demo_internal_dirs:
                logger.debug("Skipping internal demo directory: %s", app_dir)
                continue
            if app_dir not in processed_dirs:
                self._load_test_smart(app_dir)
                processed_dirs.add(app_dir)

        # Check for demo-script.py files (demos without hop3.toml at top level)
        for demo_script in path.rglob("demo-script.py"):
            demo_dir = demo_script.parent
            if self._has_ignore_ancestor(demo_dir, path):
                continue
            if demo_dir not in processed_dirs:
                self._load_demo(demo_dir)

        # Tutorials: literate markdown files under a tutorials/ tree (validoc).
        self._scan_tutorials(path, rel_path)

    def _scan_tutorials(self, path: Path, rel_path: str) -> None:
        """Discover literate tutorial markdown files (validoc-driven).

        Restricted to tutorials trees so app/demo READMEs aren't mistaken for
        tutorials.
        """
        if "tutorials" not in rel_path:
            return
        for md in sorted(path.rglob("*.md")):
            if md.name.lower() in {"index.md", "readme.md"}:
                continue
            if self._has_ignore_ancestor(md.parent, path):
                continue
            # A source tutorial with no executable validoc blocks is pure prose
            # (e.g. a Nix explainer): it tests nothing, so it's not a runnable
            # test — skip it like index.md rather than report it as failing
            # "nothing tested". (Source tree only; the runner still fails loudly
            # if a 0-block file slips through, e.g. from a misconfigured scan.)
            if not _has_executable_blocks(md):
                logger.debug("Skipping doc-only tutorial (no exec blocks): %s", md)
                continue
            self._load_tutorial(md)

    def _load_demo(self, demo_dir: Path) -> None:
        """Load a demo directory (has demo-script.py)."""
        try:
            test_def = generate_test_definition_from_app(demo_dir)
            self._add_test(test_def)
        except Exception as e:
            logger.warning("Failed to load demo %s: %s", demo_dir, e)
            self._errors.append((demo_dir, str(e)))

    def _load_tutorial(self, md_path: Path) -> None:
        """Load a literate tutorial markdown file (validoc-driven)."""
        try:
            test_def = generate_tutorial_test_definition(md_path)
            self._add_test(test_def)
        except Exception as e:
            logger.warning("Failed to load tutorial %s: %s", md_path, e)
            self._errors.append((md_path, str(e)))

    def _load_test_smart(self, app_dir: Path) -> None:
        """Load a test using smart loading (hop3.toml + test.toml).

        This method tries to load from hop3.toml first, falling back to
        test.toml, and finally generating from app structure.
        """
        try:
            test_def = load_test_definition_smart(app_dir)
            self._add_test(test_def)
        except TestDefinitionError as e:
            logger.warning("Failed to load %s: %s", app_dir, e)
            self._errors.append((app_dir, str(e)))
        except Exception as e:
            logger.warning("Failed to load app %s: %s", app_dir, e)
            self._errors.append((app_dir, str(e)))

    def _add_test(self, test_def: TestDefinition) -> None:
        """Add a test to the catalog.

        The test name is derived from its path relative to the project root,
        ensuring uniqueness even when apps in different directories share
        the same directory name (e.g., docker-apps/wordpress vs native-apps/wordpress).
        """
        # Use relative path as the canonical name
        if test_def.app_path:
            try:
                rel = test_def.app_path.resolve().relative_to(self.root.resolve())
                test_def.name = str(rel)
            except ValueError:
                pass  # Outside project root, keep original name

        if test_def.name in self._tests:
            logger.warning("Duplicate test: %s (keeping first)", test_def.name)
            return

        self._tests[test_def.name] = test_def
        if test_def.app_path:
            self._by_path[test_def.app_path.resolve()] = test_def

    def _build_indexes(self) -> None:
        """Build tier and priority indexes."""
        self._by_tier = {}
        self._by_priority = {}

        for test in self._tests.values():
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
        """Return all discovered tests, sorted by name."""
        return sorted(self._tests.values(), key=lambda t: t.name)

    def get_test(self, name: str) -> TestDefinition | None:
        """Get a specific test by name."""
        return self._tests.get(name)

    def get_test_by_path(self, path: Path) -> TestDefinition | None:
        """Get a test by its directory path.

        Args:
            path: Path to the test directory (can be relative or absolute)

        Returns:
            TestDefinition if found, None otherwise
        """
        # Resolve to absolute path for comparison
        resolved = path.resolve()

        # Try direct lookup first
        if resolved in self._by_path:
            return self._by_path[resolved]

        # Try with root prefix if path is relative
        if not path.is_absolute():
            with_root = (self.root / path).resolve()
            if with_root in self._by_path:
                return self._by_path[with_root]

        return None

    def by_tier(self, tier: str | Tier) -> list[TestDefinition]:
        """Get tests by tier."""
        if isinstance(tier, Tier):
            tier = tier.value
        return self._by_tier.get(tier, [])

    def filter(
        self,
        tiers: list[str] | None = None,
        priorities: list[str] | None = None,
        targets: list[str] | None = None,
        tags: list[str] | None = None,
        name_pattern: str | None = None,
    ) -> list[TestDefinition]:
        """Filter tests by multiple criteria.

        Args:
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
