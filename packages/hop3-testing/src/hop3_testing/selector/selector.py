# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test selector logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3_testing.catalog.models import TargetType

if TYPE_CHECKING:
    from collections.abc import Callable

    from hop3_testing.catalog.models import TestDefinition
    from hop3_testing.catalog.scanner import Catalog

    from .modes import ModeConfig


@dataclass(frozen=True)
class Selector:
    """
    Selects tests based on mode and additional filters.

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
        """
        Select tests based on mode and filters.

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

        # A curated profile carries an explicit test list: return exactly those,
        # in order, ignoring the tier/priority/target filters (which it leaves
        # empty). Order matters — it preserves demo01→demoNN sequencing.
        if mode_config.tests:
            return self._get_specific_tests(mode_config.tests)

        # Apply mode-based filtering
        tests = self.catalog.filter(
            tiers=mode_config.tiers,
            priorities=mode_config.priorities,
            targets=mode_config.targets,
            tags=tags,
            name_pattern=name_pattern,
        )

        # Coverage modes keep a representative subset that exercises every
        # significant case.  ``tag-coverage`` covers each individual tag value;
        # ``combo-coverage`` (and the back-compat alias ``coverage``) cover each
        # observed 5-tuple combination.
        if mode_config.representative:
            if mode_config.name == "tag-coverage":
                tests = select_tag_coverage(tests)
            else:
                tests = select_combo_coverage(tests)

        return tests

    def _get_specific_tests(self, names: list[str]) -> list[TestDefinition]:
        """
        Get specific tests by name.

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
        """
        Select tests that can run on a specific target type.

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


def _tag_cells(test: TestDefinition) -> set[str]:
    """
    Individual tag values this test exercises — one cell per axis value.

    Tag axes: builder, toolchain, addon, category, spec.  Each axis value
    appears as an independent cell, so a test contributes multiple cells
    (e.g. ``builder:native``, ``toolchain:python``, ``addon:mysql``,
    ``category:deployment``, ``spec:hop3toml``).
    """
    cells: set[str] = set()
    if test.metadata.builder:
        cells.add(f"builder:{test.metadata.builder}")
    if test.metadata.toolchain:
        cells.add(f"toolchain:{test.metadata.toolchain}")
    if test.metadata.spec:
        cells.add(f"spec:{test.metadata.spec}")
    cells.add(f"category:{test.runner_type}")
    cells.update(f"addon:{svc}" for svc in test.requirements.services)
    return cells


def _combo_cells(test: TestDefinition) -> set[str]:
    """
    A single cell representing the full 5-tuple this test exercises.

    The cell is a single string encoding the observed combination:
    ``combo:<builder>/<toolchain>/<addons>/<category>/<spec>``.
    Two tests that share the exact same 5-tuple produce the same cell,
    so set-cover keeps only one of them.
    """
    builder = test.metadata.builder or "?"
    toolchain = test.metadata.toolchain or "?"
    addons = "+".join(sorted(test.requirements.services)) or "-"
    category = test.runner_type
    spec = test.metadata.spec or "?"
    return {f"combo:{builder}/{toolchain}/{addons}/{category}/{spec}"}


def _sort_key(test: TestDefinition) -> tuple[int, int, str]:
    return (
        _PRIORITY_ORDER.get(test.priority.value, 99),
        _TIER_ORDER.get(test.tier.value, 99),
        test.name,
    )


def reduce_to_representatives(
    tests: list[TestDefinition],
    *,
    cell_fn: Callable[[TestDefinition], set[str]] = _tag_cells,
) -> list[TestDefinition]:
    """
    Minimal subset that covers every cell (greedy set-cover).

    ``cell_fn`` maps each test to the set of cells it covers.  We greedily pick
    the highest-priority/fastest test that adds the most new cells until every
    coverable cell is covered.  Deterministic: ties break by (priority, tier,
    name).

    Tests marked ``expects_failure`` are excluded: a coverage suite proves the
    platform works, and an app that is *meant* to fail represents nothing.
    """
    tests = [t for t in tests if not t.expects_failure]
    if not tests:
        return []

    cells = {t.name: cell_fn(t) for t in tests}
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


def select_tag_coverage(tests: list[TestDefinition]) -> list[TestDefinition]:
    """
    Minimal subset covering every individual tag value at least once.

    Each tag axis value (e.g. ``builder:nix``, ``toolchain:go``,
    ``addon:mysql``) must appear in at least one selected test.
    """
    return reduce_to_representatives(tests, cell_fn=_tag_cells)


def select_combo_coverage(tests: list[TestDefinition]) -> list[TestDefinition]:
    """
    Minimal subset covering every observed 5-tuple combination at least once.

    Each unique (builder, toolchain, addon-set, category, spec) combination
    must be represented by at least one test.
    """
    return reduce_to_representatives(tests, cell_fn=_combo_cells)
