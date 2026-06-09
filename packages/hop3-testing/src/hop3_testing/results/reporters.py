# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Output reporters for test results."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from hop3_testing.util.timing import format_duration

if TYPE_CHECKING:
    from hop3_testing.runners.base import TestResult


def _phase_breakdown(result: TestResult) -> list[tuple[str, float]]:
    """Sum a test's validation durations by phase (deploy, http, script, ...)."""
    by_phase: dict[str, float] = {}
    for v in result.validation_results:
        by_phase[v.type_name] = by_phase.get(v.type_name, 0.0) + v.duration
    return [(name, dur) for name, dur in by_phase.items() if dur > 0]


def narrate_timings(results: list[TestResult], *, output: TextIO | None = None) -> None:
    """Print a per-test phase-timing breakdown (the ``--narrate`` reporter).

    Preserves the demo harness's timing narration: where the wall-clock went,
    per test and per phase (deploy / http / script / ...), slowest first.
    """
    out = output or sys.stdout
    if not results:
        return

    ordered = sorted(results, key=lambda r: r.total_duration, reverse=True)
    total_wall = sum(r.total_duration for r in results)
    total_deploy = 0.0

    print("\nTIMINGS (slowest first)", file=out)
    for r in ordered:
        print(f"  {format_duration(r.total_duration):>10}  {r.test.name}", file=out)
        phases = _phase_breakdown(r)
        if phases:
            parts = " · ".join(f"{name} {format_duration(d)}" for name, d in phases)
            print(f"              {parts}", file=out)
        total_deploy += sum(d for name, d in phases if name == "deploy")

    slowest = ordered[0]
    print(
        f"  ── total wall {format_duration(total_wall)}"
        f" across {len(results)} tests"
        f" · deploy {format_duration(total_deploy)}"
        f" · slowest {slowest.test.name} ({format_duration(slowest.total_duration)})",
        file=out,
    )


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
            mark = self._colorize("✗", "red")
            print(f"  {mark} {name}", file=self.output)

            # Headline-first (ADR 043 §7): the bundle's classifier verdict +
            # the `why` pointer say what's wrong and where to look. The full
            # sections stay on disk — terse on screen, rich in the artifact.
            if r.bundle is not None:
                for line in r.bundle.headline.splitlines():
                    print(f"      {line}", file=self.output)
                continue

            # Legacy path — runners not yet wired to the bundle.
            cause = self._extract_root_cause(r.error or "validation failed")
            print(f"      {cause}", file=self.output)
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

    def _extract_app_log_tail(self, result: TestResult, *, max_lines: int = 30) -> str:
        """Extract the most-relevant tail of app logs from runtime diagnostics.

        ``collect_runtime_logs`` produces a labelled blob with per-section
        ``--- Title ---`` headers. Two relevant sections:

        - **App log files** — uWSGI / native deployer logs at
          ``/home/hop3/apps/<app>/log/<name>.log``. Per-file markers look
          like ``--- /home/hop3/apps/<app>/log/<file>.log ---``.
        - **Docker container logs** — for docker-based apps, the per-app
          uWSGI dir is empty. Per-container markers look like
          ``--- <container-name> ---``.

        We try native logs first (web.* > worker.* > other), then fall
        back to docker container logs. This way the inline tail is
        useful for both deployer types — previously docker apps showed
        the literal ``tail: cannot open ...`` shell error here, which
        was uniformly unhelpful.
        """
        blob = getattr(result, "runtime_logs", "") or ""
        if not blob:
            return ""

        native = self._extract_native_log_tail(blob, max_lines=max_lines)
        if native:
            return native
        return self._extract_docker_logs_tail(blob, max_lines=max_lines)

    def _extract_native_log_tail(self, blob: str, *, max_lines: int) -> str:
        """Tail of the most-interesting uWSGI/native log file, if any."""
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

        return self._format_tail(f"[{picked_path}]", picked_content, max_lines)

    def _extract_docker_logs_tail(self, blob: str, *, max_lines: int) -> str:
        """Tail of the first container's docker logs, if any.

        Used as a fallback when the native log section had no real
        files (typical for docker-based apps where uWSGI isn't involved).
        """
        import re  # noqa: PLC0415

        # The "Docker container logs ..." section header is the last in
        # collect_runtime_logs — anything after it is in scope.
        section_re = re.compile(
            r"^---\s+Docker container logs[^-\n]*---\s*$",
            re.MULTILINE,
        )
        match = section_re.search(blob)
        if not match:
            return ""
        section_body = blob[match.end() :]

        # Skip past any subsequent top-level section header (defensive,
        # in case collect_runtime_logs ever appends new sections after
        # this one).
        next_section = re.search(
            r"^===\s+",
            section_body,
            re.MULTILINE,
        )
        if next_section:
            section_body = section_body[: next_section.start()]

        # Per-container markers: `--- <container-name> ---` (no path).
        container_re = re.compile(r"^---\s+(\S[^\n]*?)\s+---\s*$", re.MULTILINE)
        matches = list(container_re.finditer(section_body))
        if not matches:
            return ""

        first = matches[0]
        end = matches[1].start() if len(matches) > 1 else len(section_body)
        container_name = first.group(1)
        content = section_body[first.end() : end].strip()

        # Skip uninformative section bodies emitted by the collector.
        if not content or content in {
            "(empty)",
            "(docker not installed)",
            "(no docker containers matching app name)",
        }:
            return ""

        return self._format_tail(
            f"[docker logs {container_name}]",
            content,
            max_lines,
        )

    def _format_tail(self, header: str, content: str, max_lines: int) -> str:
        """Render the last ``max_lines`` of ``content`` with a header line."""
        lines = content.splitlines()
        if len(lines) > max_lines:
            lines = [
                f"... ({len(lines) - max_lines} earlier lines elided)",
                *lines[-max_lines:],
            ]
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

    def _print_per_app_results(self, results: list[TestResult]) -> None:
        """Print one line per test: `- <name> (<path>): OK|FAIL`.

        Sorted by pass/fail (failures first for triage visibility),
        then by name within each group. Path is shown relative to the
        current working directory when possible; falls back to the
        absolute app_path for tests whose source lives outside cwd.
        """
        if not results:
            return

        print(file=self.output)
        print(
            self._colorize("Per-app results:", "bold"),
            file=self.output,
        )

        # Failed first (operators care most), then passed; alphabetical
        # within each group.
        ordered = sorted(results, key=lambda r: (r.passed, self._app_display_path(r)))
        for r in ordered:
            status = (
                self._colorize("OK", "green")
                if r.passed
                else self._colorize("FAIL", "red")
            )
            name = r.test.name
            path = self._app_display_path(r)
            # If `name` is already the path (scanner rewrites it for
            # apps under the project root), skip the parenthetical.
            if name == path:
                print(f"  - {name}: {status}", file=self.output)
            else:
                print(f"  - {name} ({path}): {status}", file=self.output)

    @staticmethod
    def _app_display_path(result: TestResult) -> str:
        """Best-effort relative path for display.

        Prefer the app_path (directory containing hop3.toml/test.toml),
        fall back to source_path's parent, fall back to '?'. Relative
        to cwd when possible so we don't show long absolute paths.
        """
        path = result.test.app_path
        if path is None and result.test.source_path is not None:
            path = result.test.source_path.parent
        if path is None:
            return "?"
        try:
            return str(path.resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            return str(path)

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

        # Per-app status listing. `test.name` can be either the
        # `metadata.id` (short — e.g., "directus") or the relative
        # path (e.g., "apps/bad/test-apps-bad/focalboard")
        # depending on how it reached the catalog. Short names collide
        # across apps/bad/ variants (multiple "focalboard"s), so we
        # always show the app_path alongside to disambiguate.
        self._print_per_app_results(results)

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
