# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Output reporters for test results."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from hop3_testing.runners.base import TestResult


@dataclass
class ConsoleReporter:
    """Reports test results to the console."""

    verbose: bool = False
    """Whether to show detailed output."""

    quiet: bool = False
    """Whether to suppress recap (show only pass/fail summary)."""

    output: TextIO = field(default_factory=lambda: sys.stdout)
    """Output stream."""

    color: bool = True
    """Whether to use colored output (before TTY check)."""

    def __post_init__(self) -> None:
        """Adjust color setting based on TTY detection."""
        self.color = (
            self.color and hasattr(self.output, "isatty") and self.output.isatty()
        )

    def _colorize(self, text: str, color: str) -> str:
        """Apply ANSI color code to text."""
        if not self.color:
            return text

        colors = {
            "green": "\033[92m",
            "red": "\033[91m",
            "yellow": "\033[93m",
            "blue": "\033[94m",
            "reset": "\033[0m",
            "bold": "\033[1m",
        }

        return f"{colors.get(color, '')}{text}{colors['reset']}"

    def report_test(self, result: TestResult) -> None:
        """Report a single test result.

        Args:
            result: The test result to report
        """
        if result.passed:
            status = self._colorize("PASS", "green")
        else:
            status = self._colorize("FAIL", "red")

        duration = f"{result.total_duration:.2f}s"

        # Note: test name is already printed by the runner, just add status
        print(f"{status} ({duration})", file=self.output)

        if not result.passed and (self.verbose or result.error):
            if result.error:
                print(f"  Error: {result.error}", file=self.output)

            for v in result.failed_validations:
                print(f"  - {v.type_name}: {v.message}", file=self.output)

    def summary(self, results: list[TestResult]) -> None:
        """Print summary of all results.

        Args:
            results: List of all test results
        """
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        total_duration = sum(r.total_duration for r in results)

        print(file=self.output)
        print("=" * 60, file=self.output)

        if failed == 0:
            print(
                self._colorize(f"All {total} tests passed!", "green"),
                file=self.output,
            )
        else:
            print(
                self._colorize(f"{failed} of {total} tests failed", "red"),
                file=self.output,
            )

        print(f"Total time: {total_duration:.2f}s", file=self.output)
        print("=" * 60, file=self.output)

        if failed > 0 and self.verbose:
            print(file=self.output)
            print("Failed tests:", file=self.output)
            for r in results:
                if not r.passed:
                    print(
                        f"  - {r.test.name}: {r.error or 'validation failed'}",
                        file=self.output,
                    )

        # Show recap unless quiet mode
        if not self.quiet and results:
            self._print_recap(results, total_duration)

    def _print_recap(self, results: list[TestResult], total_duration: float) -> None:
        """Print a recap of what was tested.

        Args:
            results: List of all test results
            total_duration: Total time for all tests
        """
        print(file=self.output)
        print(self._colorize("Recap:", "bold"), file=self.output)

        # Group by category
        by_category: dict[str, list[TestResult]] = {}
        for r in results:
            cat = r.test.category or "uncategorized"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(r)

        # Group by tier
        by_tier: dict[str, int] = {}
        for r in results:
            tier = r.test.tier or "unknown"
            by_tier[tier] = by_tier.get(tier, 0) + 1

        # Collect unique technologies/covers
        technologies: set[str] = set()
        for r in results:
            if hasattr(r.test, "metadata") and r.test.metadata:
                covers = getattr(r.test.metadata, "covers", []) or []
                technologies.update(covers)

        # Print category breakdown
        for cat, cat_results in sorted(by_category.items()):
            passed = sum(1 for r in cat_results if r.passed)
            total = len(cat_results)
            status = (
                self._colorize("✓", "green")
                if passed == total
                else self._colorize("✗", "red")
            )
            print(f"  {status} {cat}: {passed}/{total} passed", file=self.output)

        # Print tier breakdown
        if len(by_tier) > 1:
            tier_parts = [f"{tier}={count}" for tier, count in sorted(by_tier.items())]
            print(f"  Tiers: {', '.join(tier_parts)}", file=self.output)

        # Print technologies if available
        if technologies:
            tech_list = sorted(technologies)
            if len(tech_list) > 10:
                tech_str = (
                    ", ".join(tech_list[:10]) + f", ... (+{len(tech_list) - 10} more)"
                )
            else:
                tech_str = ", ".join(tech_list)
            print(f"  Covers: {tech_str}", file=self.output)

        # Print timing info
        avg_time = total_duration / len(results) if results else 0
        print(f"  Avg time per test: {avg_time:.1f}s", file=self.output)

    def report_package_result(self, result: TestResult) -> None:
        """Report result of package validation.

        Args:
            result: The package test result
        """
        print(file=self.output)
        print("=" * 60, file=self.output)
        print("Package Validation Result", file=self.output)
        print("=" * 60, file=self.output)

        if result.passed:
            print(
                self._colorize("Package validation PASSED", "green"), file=self.output
            )
        else:
            print(self._colorize("Package validation FAILED", "red"), file=self.output)

        print(f"Duration: {result.total_duration:.2f}s", file=self.output)

        if result.error:
            print(f"Error: {result.error}", file=self.output)

        print(file=self.output)
        print(
            f"Validations: {len(result.passed_validations)}/{len(result.validation_results)} passed",
            file=self.output,
        )

        if result.failed_validations:
            print(file=self.output)
            print("Failed validations:", file=self.output)
            for v in result.failed_validations:
                print(f"  - {v.type_name}: {v.message}", file=self.output)

        print("=" * 60, file=self.output)
