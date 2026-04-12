# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Per-app log file writer for test runs."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_testing.runners.base import TestResult


class TestLogWriter:
    """Writes per-app log files to a logs directory.

    Each test gets its own log file containing:
    - Test metadata (name, tier, priority)
    - Deployment logs
    - Validation results
    - Debug info (if test failed)
    """

    def __init__(self, logs_dir: Path | None = None):
        """Initialize log writer.

        Args:
            logs_dir: Directory for log files. If None, logging is disabled.
        """
        self.logs_dir = logs_dir
        if logs_dir:
            logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        """Check if logging is enabled."""
        return self.logs_dir is not None

    def write_test_log(
        self,
        result: TestResult,
        debug_output: str | None = None,
    ) -> Path | None:
        """Write log file for a single test.

        Args:
            result: Test result to log
            debug_output: Optional debug output to include

        Returns:
            Path to the log file, or None if logging disabled
        """
        if not self.enabled or self.logs_dir is None:
            return None

        test = result.test
        log_file = self.logs_dir / f"{test.name}.log"

        lines = [
            f"=== Log for {test.name} ===",
            f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Test: {test.name}",
            f"Type: {test.runner_type}",
            f"Tier: {test.tier.value}",
            f"Priority: {test.priority.value}",
            f"Duration: {result.total_duration:.2f}s",
            f"Result: {'PASS' if result.passed else 'FAIL'}",
            "",
        ]

        if result.error:
            lines.extend([
                "=== Error ===",
                result.error,
                "",
            ])

        if result.deploy_logs:
            lines.extend([
                "=== Deployment Logs ===",
                result.deploy_logs,
                "",
            ])

        lines.append("=== Validations ===")
        for v in result.validation_results:
            status = "PASS" if v.passed else "FAIL"
            lines.append(f"[{status}] {v.type_name}: {v.message}")
            if v.details:
                for key, value in v.details.items():
                    lines.append(f"  {key}: {value}")
        lines.append("")

        if debug_output:
            lines.extend([
                "=== Debug Info ===",
                debug_output,
                "",
            ])

        lines.extend([
            f"=== End of log for {test.name} ===",
            f"Ended at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        ])

        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("\n".join(lines))
        return log_file
