# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test selector logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3_testing.catalog.models import TargetType

from .modes import ModeConfig

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition
    from hop3_testing.catalog.scanner import Catalog


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
            categories=mode_config.categories,
            tiers=mode_config.tiers,
            priorities=mode_config.priorities,
            targets=mode_config.targets,
            tags=tags,
            name_pattern=name_pattern,
        )

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

    def estimate_duration(self, tests: list[TestDefinition]) -> int:
        """Estimate total duration for running tests.

        Args:
            tests: List of tests

        Returns:
            Estimated duration in seconds
        """
        # Simple estimation based on tier
        tier_durations = {
            "fast": 10,
            "medium": 60,
            "slow": 300,
            "very-slow": 900,
        }

        total = 0
        for test in tests:
            total += tier_durations.get(test.tier.value, 60)

        return total

    def group_by_category(
        self,
        tests: list[TestDefinition],
    ) -> dict[str, list[TestDefinition]]:
        """Group tests by category.

        Args:
            tests: List of tests

        Returns:
            Dictionary mapping category to tests
        """
        groups: dict[str, list[TestDefinition]] = {}

        for test in tests:
            category = test.category.value
            if category not in groups:
                groups[category] = []
            groups[category].append(test)

        return groups

    def group_by_tier(
        self,
        tests: list[TestDefinition],
    ) -> dict[str, list[TestDefinition]]:
        """Group tests by tier.

        Args:
            tests: List of tests

        Returns:
            Dictionary mapping tier to tests
        """
        groups: dict[str, list[TestDefinition]] = {}

        for test in tests:
            tier = test.tier.value
            if tier not in groups:
                groups[tier] = []
            groups[tier].append(test)

        return groups
