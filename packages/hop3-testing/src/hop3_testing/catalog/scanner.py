# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Test catalog scanner.

Discovers test.toml files and hop3.toml-based test apps to build a unified catalog.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .loader import (
    TestDefinitionError,
    _under_bad_dir,
    generate_test_definition_from_app,
    generate_tutorial_test_definition,
    load_test_definition_smart,
)
from .models import TargetType, TestDefinition, Tier

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

logger = logging.getLogger(__name__)

IGNORE_FILE = "HOP3_TEST_IGNORE"

# A DEFERRED.md under apps/bad/** is OVERLOADED: it marks BOTH a deploys-fine
# business-drop (e.g. focalboard — "dropped for business reasons, not a platform
# limitation") AND a genuine platform blocker (e.g. monica — a "## Blocker" that
# really fails to deploy). Only the former is skipped from the run (it is not a
# negative test); a genuine blocker STAYS a negative test, so DEFERRED.md
# existence alone must NOT be the skip signal. The business-drop is distinguished
# by the deliberate "not a platform limitation" marker line in its DEFERRED.md
# (CLAUDE.md's "business-reasons decision" language). (audit C6)
DEFERRED_FILE = "DEFERRED.md"
_BUSINESS_DROP_MARKER = "not a platform limitation"

# Executable validoc fences (same set the tutorial runner counts). A tutorial
# markdown with none of these runs no commands — it's documentation, not a test.
_VALIDOC_BLOCK_RE = re.compile(r"^```(?:bash\s+exec|output|file)\b", re.MULTILINE)


def _has_executable_blocks(md_path: Path) -> bool:
    """True if a tutorial markdown has at least one executable validoc block."""
    try:
        return bool(_VALIDOC_BLOCK_RE.search(md_path.read_text(encoding="utf-8")))
    except OSError:
        return False


#: Local ``apps/`` families that hold platform test fixtures rather than
#: applications anyone installs. These stay in this repository: they exercise
#: builders, toolchains and error paths, and have no place in a catalog of
#: things to offer an operator.
FIXTURE_FAMILIES = ("test-apps-procfile", "test-apps-nix", "test-apps-nix-gen")

#: Every maturity status a catalog recipe can live under (ADR 059). The folder
#: *is* the status, so selecting a status is selecting a directory — there is
#: nothing to filter and nothing to keep in sync.
CATALOG_STATUSES = ("golden", "beta", "alpha", "broken", "retired")

#: Catalog statuses worth deploying by default: the ones the catalog publishes
#: (ADR 059). ``alpha`` and ``broken`` are kept as a record, and running them
#: would report failures already known and written down.
CATALOG_SUITES = ("golden", "beta")


def default_catalog_apps(root: Path) -> Path | None:
    """The sibling catalog checkout's ``apps/``, if there is one."""
    candidate = root.parent / "hop3-catalog" / "apps"
    return candidate if candidate.is_dir() else None


def catalog_status_paths(root: Path, statuses: Iterable[str]) -> list[str]:
    """
    Scan paths for the named maturity statuses.

    Status is a *selection of directories*, not a property to filter on: a
    filter would quietly match nothing whenever the requested status lay outside
    the default scan set, which is the shape of a silent skip.

    Raises:
        ValueError: on an unknown status name, or with no catalog checkout —
            either way the run would otherwise report "0 tests" and exit clean.
    """
    unknown = sorted(set(statuses) - set(CATALOG_STATUSES))
    if unknown:
        msg = (
            f"Unknown catalog status: {', '.join(unknown)}. "
            f"Known statuses: {', '.join(CATALOG_STATUSES)}"
        )
        raise ValueError(msg)

    catalog_apps = default_catalog_apps(root)
    if catalog_apps is None:
        msg = (
            f"No catalog checkout at {root.parent / 'hop3-catalog'}: "
            "cannot select apps by status. Clone it beside this repository."
        )
        raise ValueError(msg)

    missing = [s for s in statuses if not (catalog_apps / s).is_dir()]
    if missing:
        msg = f"Catalog has no {', '.join(missing)} directory under {catalog_apps}"
        raise ValueError(msg)

    return [str(catalog_apps / s) for s in statuses]


def default_scan_paths(root: Path) -> list[str]:
    """
    Default scan set: the catalog's published apps, plus this repo's fixtures.

    The single source of truth for "what to scan when no paths are given",
    shared by the ``hop3-test`` CLI and the Test Lab (which used to keep its own
    copy). Scans the *source* tutorials tree (``docs/tutorials``), not the
    rendered one — validoc's executable ``bash exec``/``output``/``file`` fences
    are stripped out of ``docs/src/tutorials`` during the docs build, so scanning
    that yields a vacuous "0 passed".

    **Two roots, deliberately.** Real applications live in the catalog and the
    fixtures live here, so neither tree alone is the answer. This repository
    once carried its own copies of the applications too; they were forks that
    drifted, and `hop3-test` was exercising them rather than the recipes an
    operator installs.

    Absolute paths are returned for the catalog and relative ones for this repo;
    ``Catalog.scan`` joins both correctly. To run against a different checkout,
    pass its path to `hop3-test run` directly — an option for it would be a
    second way to say the same thing.
    """
    paths: list[str] = []

    catalog_apps = default_catalog_apps(root)
    if catalog_apps:
        paths += [
            str(catalog_apps / suite)
            for suite in CATALOG_SUITES
            if (catalog_apps / suite).is_dir()
        ]

    apps_dir = root / "apps"
    if apps_dir.is_dir():
        paths += [
            str(child.relative_to(root))
            for child in sorted(apps_dir.iterdir())
            if child.is_dir() and child.name in FIXTURE_FAMILIES
        ]
    if (root / "demos").is_dir():
        paths.append("demos")
    if (root / "docs/tutorials").is_dir():
        paths.append("docs/tutorials")
    elif (root / "docs/src/tutorials").is_dir():
        paths.append("docs/src/tutorials")
    return paths


class Catalog:
    """
    Discovers and indexes all tests in the project.

    The catalog discovers test apps by scanning explicitly provided paths.
    Any subdirectory containing hop3.toml or test.toml files is included.
    Directories containing a HOP3_TEST_IGNORE file are excluded.
    """

    def __init__(self, root: Path | None = None):
        """
        Initialize the catalog.

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
        """
        Scan directories for test definitions.

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

    def _has_demo_ancestor(self, path: Path, root: Path) -> bool:
        """
        True if ``path`` sits inside a demo directory (one with demo-script.py).

        A demo's inner ``app/`` (``demos/demoNN/app/``, carrying its own
        ``hop3.toml``) is the demo's private deploy target, driven by
        ``demo-script.py`` — not a standalone test. Walk ancestors up to and
        including ``root`` so this holds however the scan entered: ``demos/``,
        ``demos/demoNN``, or ``demos/demoNN/app``. (The old child-scan only
        worked when the scan path was the ``demos/`` parent, so a demo dir passed
        directly leaked its inner app — the demo60/app regression.)
        """
        current = path.parent
        while True:
            if (current / "demo-script.py").exists():
                return True
            if current in {root, current.parent}:
                return False
            current = current.parent

    def _has_ignore_ancestor(self, path: Path, root: Path) -> bool:
        """Check if any ancestor of path (up to root) contains HOP3_TEST_IGNORE."""
        current = path.parent
        while current not in {root, current.parent}:
            if (current / IGNORE_FILE).exists():
                return True
            current = current.parent
        return False

    def _is_deferred_business_drop(self, app_dir: Path) -> bool:
        """
        True only for a deploys-fine business-drop under apps/bad/** — a
        DEFERRED.md that explicitly marks itself "not a platform limitation".

        Such apps are skipped from the run (they aren't negative tests). A
        genuine bad recipe — a DEFERRED.md documenting a real ``## Blocker`` that
        fails to deploy, or no DEFERRED.md at all — is NOT skipped; it stays a
        negative test so its builder-rejection coverage is preserved (audit C6).
        """
        if not _under_bad_dir(app_dir):
            return False
        deferred = app_dir / DEFERRED_FILE
        if not deferred.is_file():
            return False
        try:
            text = deferred.read_text(encoding="utf-8").lower()
        except OSError:
            return False
        return _BUSINESS_DROP_MARKER in text

    def _scan_directory(self, path: Path, rel_path: str) -> None:  # ruff:ignore[complex-structure, too-many-branches]
        """
        Scan a single directory for tests.

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

        # Check for test.toml files recursively (sorted for deterministic order)
        for test_toml in sorted(path.rglob("test.toml")):
            app_dir = test_toml.parent
            if self._has_ignore_ancestor(app_dir, path):
                continue
            if self._is_deferred_business_drop(app_dir):
                logger.debug("Skipping deferred business-drop: %s", app_dir)
                continue
            # Skip a demo's private deploy target (demos/demoNN/app/).
            if self._has_demo_ancestor(app_dir, path):
                logger.debug("Skipping internal demo directory: %s", app_dir)
                continue
            if app_dir not in processed_dirs:
                self._load_test_smart(app_dir)
                processed_dirs.add(app_dir)

        # Check for hop3.toml files recursively (that don't have test.toml)
        for hop3_toml in sorted(path.rglob("hop3.toml")):
            app_dir = hop3_toml.parent
            if self._has_ignore_ancestor(app_dir, path):
                continue
            if self._is_deferred_business_drop(app_dir):
                logger.debug("Skipping deferred business-drop: %s", app_dir)
                continue
            # Skip a demo's private deploy target (demos/demoNN/app/).
            if self._has_demo_ancestor(app_dir, path):
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
        """
        Discover literate tutorial markdown files (validoc-driven).

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
        """
        Load a test using smart loading (hop3.toml + test.toml).

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
        """
        Add a test to the catalog.

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
        """
        Get a test by its directory path.

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
        """
        Filter tests by multiple criteria.

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
