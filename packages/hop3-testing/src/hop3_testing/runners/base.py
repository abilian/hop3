# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Base types for test runners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition, Validation


@dataclass
class ValidationResult:
    """Result of a single validation check.

    Supports two modes:
    - With a Validation object (for test.toml validations)
    - With a validation_type string (for internal lifecycle checks like deploy)
    """

    passed: bool
    """Whether the validation passed."""

    message: str
    """Human-readable result message."""

    duration: float
    """Time taken in seconds."""

    validation: Validation | None = None
    """The validation that was run (for test.toml validations)."""

    validation_type: str | None = None
    """Simple type string (for internal validations like deploy, deploy_check)."""

    details: dict | None = None
    """Optional additional details (e.g., response body)."""

    @property
    def type_name(self) -> str:
        """Get the validation type name."""
        if self.validation:
            return self.validation.type
        return self.validation_type or "unknown"


@dataclass
class TestResult:
    """Complete result of running a test."""

    test: TestDefinition
    """The test definition that was run."""

    passed: bool
    """Whether the test passed overall."""

    validation_results: list[ValidationResult] = field(default_factory=list)
    """Results of individual validations."""

    deploy_logs: str = ""
    """Logs from the deployment phase."""

    total_duration: float = 0.0
    """Total time taken in seconds."""

    error: str | None = None
    """Error message if test failed before validations."""

    @property
    def failed_validations(self) -> list[ValidationResult]:
        """Get list of failed validations."""
        return [v for v in self.validation_results if not v.passed]

    @property
    def passed_validations(self) -> list[ValidationResult]:
        """Get list of passed validations."""
        return [v for v in self.validation_results if v.passed]

    def summary(self) -> str:
        """Get a summary string for the result."""
        status = "PASS" if self.passed else "FAIL"
        validation_summary = f"{len(self.passed_validations)}/{len(self.validation_results)} validations passed"

        lines = [
            f"[{status}] {self.test.name}",
            f"  Duration: {self.total_duration:.2f}s",
            f"  {validation_summary}",
        ]

        if self.error:
            lines.append(f"  Error: {self.error}")

        for v in self.failed_validations:
            lines.append(f"  - {v.type_name}: {v.message}")

        return "\n".join(lines)
