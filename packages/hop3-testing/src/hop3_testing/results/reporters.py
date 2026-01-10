# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Output reporters for test results."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from ..runners.base import TestResult


class ConsoleReporter:
    """Reports test results to the console."""

    def __init__(
        self,
        verbose: bool = False,
        output: TextIO | None = None,
        color: bool = True,
    ):
        """Initialize the reporter.

        Args:
            verbose: Whether to show detailed output
            output: Output stream (defaults to stdout)
            color: Whether to use colored output
        """
        self.verbose = verbose
        self.output = output or sys.stdout
        self.color = color and hasattr(self.output, "isatty") and self.output.isatty()

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

        name = result.test.name
        duration = f"{result.total_duration:.2f}s"

        print(f"[{status}] {name} ({duration})", file=self.output)

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
