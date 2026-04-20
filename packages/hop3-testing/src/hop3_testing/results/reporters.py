# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Output reporters for test results."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from pathlib import Path

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

    logs_dir: Path | None = None
    """Per-test log directory for cross-reference in failure summary."""

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

            # Show deploy logs only when they add info beyond the error
            # (e.g., for HTTP failures, not for deploy failures where
            # the error already contains the full output)
            if result.deploy_logs and result.error:
                error_str = result.error or ""
                if "Deploy failed" not in error_str:
                    log_tail = result.deploy_logs.strip()
                    if log_tail and len(log_tail) > 20:
                        if len(log_tail) > 1500:
                            log_tail = log_tail[-1500:]
                        print("\n  --- Deploy output ---", file=self.output)
                        for line in log_tail.splitlines():
                            print(f"  {line}", file=self.output)
                        print("  ---", file=self.output)

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

        # Always list failed tests with root cause + log pointer.
        # Previously gated by --verbose, which hid actionable info on
        # the common "part of a large batch failed, which ones?" case.
        if failed > 0:
            self._print_failed_tests(results)

        # Show recap unless quiet mode
        if not self.quiet and results:
            self._print_recap(results, total_duration)

    def _print_failed_tests(self, results: list[TestResult]) -> None:
        """Print the list of failed tests with a one-line root cause,
        the tail of the app's own stderr log (the usually-interesting
        part), and a pointer to each test's full log file.
        """
        print(file=self.output)
        print(self._colorize("Failed tests:", "bold"), file=self.output)
        for r in results:
            if r.passed:
                continue
            name = r.test.name
            cause = self._extract_root_cause(r.error or "validation failed")
            mark = self._colorize("✗", "red")
            print(f"  {mark} {name}", file=self.output)
            print(f"      {cause}", file=self.output)

            # Surface the app's own stderr inline. The full per-test
            # log file has everything; but 99% of the time the app's
            # web.log / worker.log tail is what a developer actually
            # needs to see, and hiding it in a file the user has to
            # open defeats the purpose of our diagnostics collection.
            app_tail = self._extract_app_log_tail(r)
            if app_tail:
                print(
                    self._colorize("      app stderr (tail):", "yellow"),
                    file=self.output,
                )
                for line in app_tail.splitlines():
                    print(f"        {line}", file=self.output)

            log_file = self._log_file_for(r)
            if log_file:
                print(f"      full log: {log_file}", file=self.output)

        if self.logs_dir:
            print(file=self.output)
            print(
                self._colorize(f"Full per-test logs: {self.logs_dir}/", "yellow"),
                file=self.output,
            )

    def _extract_app_log_tail(
        self, result: TestResult, *, max_lines: int = 30
    ) -> str:
        """Extract the tail of the app's own stderr from the runtime logs.

        ``collect_runtime_logs`` writes all files under
        ``/home/hop3/apps/<app>/log/*.log`` separated by ``--- <path> ---``
        markers. We prefer ``web.*.log`` (where attach-daemon stderr lands)
        and fall back to other kinds if no web log exists.
        """
        blob = getattr(result, "runtime_logs", "") or ""
        if not blob:
            return ""

        # Split on per-file markers from runtime_diagnostics.py: the shell
        # loop emits `--- <absolute-path> ---` before each file's content.
        # We also track ANY `--- Title ---` delimiter so the content we
        # extract doesn't leak past the "App log files" section boundary
        # into the next section (e.g. "Docker container logs").
        import re  # noqa: PLC0415

        any_marker = re.compile(r"^---\s+.+?\s+---\s*$", re.MULTILINE)
        file_marker = re.compile(r"/home/hop3/apps/[^\s]+\.log")

        per_file: list[tuple[str, str]] = []
        markers = list(any_marker.finditer(blob))
        for idx, m in enumerate(markers):
            inner = m.group(0).strip("- \n\t")
            if not file_marker.fullmatch(inner):
                continue  # section header, not a per-file marker
            end = markers[idx + 1].start() if idx + 1 < len(markers) else len(blob)
            per_file.append((inner, blob[m.end() : end].strip()))

        if not per_file:
            return ""

        # Preference order: web.* (HTTP-serving worker), worker.* (background
        # workers — often the real app process in attach-daemon-style runs),
        # anything else ending in .log but not build.log (which is verbose
        # nix/docker output unhelpful for runtime failures).
        def priority(path_content: tuple[str, str]) -> int:
            path = path_content[0]
            if "/web." in path:
                return 0
            if "/worker." in path:
                return 1
            if path.endswith("/build.log"):
                return 99
            return 2

        per_file.sort(key=priority)
        picked_path, picked_content = per_file[0]
        if not picked_content or picked_content == "(empty)":
            return ""

        lines = picked_content.splitlines()
        if len(lines) > max_lines:
            lines = [f"... ({len(lines) - max_lines} earlier lines elided)"] + lines[
                -max_lines:
            ]
        header = f"[{picked_path}]"
        return "\n".join([header, *lines])

    def _log_file_for(self, result: TestResult) -> str | None:
        """Return the per-test log path written by TestLogWriter, if any."""
        if not self.logs_dir:
            return None
        return f"{self.logs_dir}/{result.test.name}.log"

    def _extract_root_cause(self, error: str) -> str:
        """Extract the single most useful line from a test error.

        Strategies (in order):
        - Known Hop3 Abort patterns ("Deployer can't ...", etc.)
        - First line containing "error:", "Error:", "Traceback"
        - Last non-empty line (often the actual exception)
        - First 160 chars if nothing else matches
        """
        if not error:
            return "(no error message)"

        lines = [ln.rstrip() for ln in error.splitlines() if ln.strip()]
        if not lines:
            return error[:160]

        # Most specific: Hop3 structured Diagnosis
        for ln in lines:
            if "can't " in ln and ":" in ln:
                return ln[:200]

        # Next: typical error markers
        markers = (
            "ImportError:",
            "ModuleNotFoundError:",
            "Permission denied",
            "hash mismatch",
            "Connection refused",
            "timed out",
            "No such file or directory",
            "error:",
            "ERROR:",
            "Error:",
        )
        for ln in lines:
            for m in markers:
                if m in ln:
                    return ln.strip()[:200]

        # Fallback: last non-empty line
        return lines[-1][:200]

    def _print_recap(self, results: list[TestResult], total_duration: float) -> None:
        """Print a recap of what was tested.

        Args:
            results: List of all test results
            total_duration: Total time for all tests
        """
        print(file=self.output)
        print(self._colorize("Recap:", "bold"), file=self.output)

        # Group by runner type
        by_runner_type: dict[str, list[TestResult]] = {}
        for r in results:
            rt = r.test.runner_type
            if rt not in by_runner_type:
                by_runner_type[rt] = []
            by_runner_type[rt].append(r)

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

        # Print runner type breakdown
        for cat, cat_results in sorted(by_runner_type.items()):
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
