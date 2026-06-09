# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test selector logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3_testing.catalog.models import TargetType

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition
    from hop3_testing.catalog.scanner import Catalog

    from .modes import ModeConfig


@dataclass(frozen=True)
class Selector:
    """Selects tests based on mode and additional filters.

    The selector works in two phases:
    1. Apply mode config to get base set of tests
    2. Apply any additional filters (tags, name pattern, etc.)
    """

    catalog: Catalog
    """The test catalog to select from."""

    def select(
        self,
        mode_config: ModeConfig,
        *,
        tags: list[str] | None = None,
        name_pattern: str | None = None,
        specific_tests: list[str] | None = None,
    ) -> list[TestDefinition]:
        """Select tests based on mode and filters.

        Args:
            mode_config: Mode configuration
            tags: Optional list of tags to filter by
            name_pattern: Optional name substring to filter by
            specific_tests: Optional list of specific test names

        Returns:
            Sorted list of matching test definitions
        """
        # If specific tests are requested, just return those
        if specific_tests:
            return self._get_specific_tests(specific_tests)

        # Apply mode-based filtering
        tests = self.catalog.filter(
            tiers=mode_config.tiers,
            priorities=mode_config.priorities,
            targets=mode_config.targets,
            tags=tags,
            name_pattern=name_pattern,
        )

        # Coverage modes keep a representative subset that still exercises every
        # significant case, with a guaranteed floor per suite.
        if mode_config.representative:
            tests = select_coverage(tests)

        return tests

    def _get_specific_tests(self, names: list[str]) -> list[TestDefinition]:
        """Get specific tests by name.

        Args:
            names: List of test names

        Returns:
            List of matching tests (in order requested)
        """
        tests = []
        for name in names:
            test = self.catalog.get_test(name)
            if test:
                tests.append(test)
        return tests

    def select_for_target(
        self,
        mode_config: ModeConfig,
        target_type: str,
        **kwargs,
    ) -> list[TestDefinition]:
        """Select tests that can run on a specific target type.

        Args:
            mode_config: Mode configuration
            target_type: Target type (docker, remote, local)
            **kwargs: Additional filters passed to select()

        Returns:
            List of tests that can run on the target
        """
        # First select based on mode
        tests = self.select(mode_config, **kwargs)

        # Then filter by target type
        target = TargetType(target_type)
        return [t for t in tests if t.can_run_on(target)]


# --- Representative (set-cover) selection ------------------------------------

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
_TIER_ORDER = {"fast": 0, "medium": 1, "slow": 2, "very-slow": 3}
_LANGUAGES = {
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
}
# Variant is encoded in the test's path-based name (see catalog scanner).
_VARIANT_RULES = (
    ("real-apps-nix-gen", "nix-template"),
    ("real-apps-nix", "nix"),
    ("real-apps-native", "native"),
    ("real-apps-docker", "docker"),
    ("test-apps-nix", "nix"),
    ("test-apps-procfile", "procfile"),
)


def _variant_of(name: str) -> str:
    """Packaging variant from a test's path-based name."""
    n = name.replace("\\", "/")
    for needle, label in _VARIANT_RULES:
        if needle in n:
            return label
    if n.startswith("demos/") or "/demos/" in n:
        return "demo"
    if "tutorials" in n or n.startswith("docs/"):
        return "tutorial"
    return "other"


def _language_of(test: TestDefinition) -> str | None:
    """Primary toolchain/language of a test, if discernible."""
    if test.metadata.language:
        return test.metadata.language.lower()
    for tag in test.metadata.covers:
        if tag.lower() in _LANGUAGES:
            return tag.lower()
    return None


def _coverage_cells(test: TestDefinition) -> set[str]:
    """The significant-case cells a single test exercises."""
    variant = _variant_of(test.name)
    cells = {f"variant:{variant}", f"category:{test.runner_type}"}
    cells |= {f"cover:{c.lower()}" for c in test.metadata.covers}
    cells |= {f"addon:{s.lower()}" for s in test.requirements.services}
    language = _language_of(test)
    if language:
        cells.add(f"lang:{language}")
        # The pairwise variant/language cells are what make the set thorough:
        # every toolchain is exercised in every packaging variant it ships in.
        cells.add(f"variant+lang:{variant}/{language}")
    return cells


def _sort_key(test: TestDefinition) -> tuple[int, int, str]:
    return (
        _PRIORITY_ORDER.get(test.priority.value, 99),
        _TIER_ORDER.get(test.tier.value, 99),
        test.name,
    )


def reduce_to_representatives(
    tests: list[TestDefinition],
) -> list[TestDefinition]:
    """Minimal subset that still covers every significant case (greedy set-cover).

    Cells are variant, category, toolchain, variant/toolchain, and addon. We
    greedily pick the highest-priority/fastest test that adds the most new
    cells until everything coverable is covered. Deterministic: ties break by
    (priority, tier, name).
    """
    if not tests:
        return []

    cells = {t.name: _coverage_cells(t) for t in tests}
    ordered = sorted(tests, key=_sort_key)

    covered: set[str] = set()
    chosen: list[TestDefinition] = []
    pool = list(ordered)

    while True:
        best: TestDefinition | None = None
        best_gain = 0
        for test in pool:  # ordered, so the first max-gain test wins ties
            gain = len(cells[test.name] - covered)
            if gain > best_gain:
                best, best_gain = test, gain
        if best is None:  # nothing left adds coverage
            break
        chosen.append(best)
        covered |= cells[best.name]
        pool.remove(best)

    return sorted(chosen, key=_sort_key)


# Minimum demos to keep in coverage mode. Demos carry little distinguishing
# metadata, so pure set-cover collapses them to ~1; this floors a representative
# smoke of the demo machinery without dragging in all ~60.
_DEMO_FLOOR = 8


def _floor_representatives(
    tests: list[TestDefinition], floor: int
) -> list[TestDefinition]:
    """Set-cover representatives, topped up to at least ``floor`` tests.

    The set-cover picks distinct-cell representatives first (so addons/covers
    are still hit); we then add the next highest-priority/fastest tests until
    the floor is met. Never drops a representative.
    """
    reps = reduce_to_representatives(tests)
    chosen = {t.name for t in reps}
    result = list(reps)
    for test in sorted(tests, key=_sort_key):
        if len(result) >= floor:
            break
        if test.name not in chosen:
            result.append(test)
            chosen.add(test.name)
    return sorted(result, key=_sort_key)


def select_coverage(tests: list[TestDefinition]) -> list[TestDefinition]:
    """Representative coverage with a guaranteed floor per suite.

    - deployment: greedy set-cover (one per variant/toolchain/addon cell);
    - tutorials: kept in full — each is a distinct documented language path;
    - demos: a representative sample floored at ``_DEMO_FLOOR``;
    - anything else: set-cover.
    """
    by_category: dict[str, list[TestDefinition]] = {}
    for test in tests:
        by_category.setdefault(test.runner_type, []).append(test)

    selected: list[TestDefinition] = []
    selected += reduce_to_representatives(by_category.pop("deployment", []))
    selected += sorted(by_category.pop("tutorial", []), key=_sort_key)
    selected += _floor_representatives(by_category.pop("demo", []), _DEMO_FLOOR)
    for remaining in by_category.values():  # any future category
        selected += reduce_to_representatives(remaining)

    return sorted(selected, key=_sort_key)
