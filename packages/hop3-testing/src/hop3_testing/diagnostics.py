# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Diagnostic collection and reporting for hop3-testing.

This module provides holistic diagnostic information across all layers
of the Hop3 system (docker, deployer, installer, server, app, etc.)
to help debug issues regardless of which layer they originate from.

Output modes:
- Console: Show on error or in --verbose mode
- File logs: test-logs/DATE_TIME/TEST_ID/PHASE.txt
- HTML report: Generated with --report html
"""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class DiagnosticEntry:
    """A single diagnostic entry.

    Represents one operation at one layer of the system.
    """

    timestamp: str
    layer: str  # e.g., "docker", "deployer", "installer", "server", "app"
    phase: str  # e.g., "setup", "deploy", "health_check", "test", "cleanup"
    operation: str  # e.g., "start_container", "run_installer", "http_check"
    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    duration: float = 0.0
    stdout: str = ""
    stderr: str = ""

    def __str__(self) -> str:
        status = "\u2713" if self.success else "\u2717"
        return f"[{self.layer}/{self.phase}] {status} {self.operation}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestRunContext:
    """Context for a test run.

    Identifies a specific test execution for logging purposes.
    """

    run_id: str  # DATE_TIME format
    test_id: str  # Composite: test_name-config (e.g., "010-flask-docker")
    test_name: str
    config: str  # e.g., "docker", "vm", "remote-dev.example.com"
    start_time: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(cls, test_name: str, config: str = "docker") -> TestRunContext:
        """Create a new test run context."""
        now = datetime.now(tz=timezone.utc)
        run_id = now.strftime("%Y%m%d_%H%M%S")
        test_id = f"{test_name}-{config}".replace(".", "-").replace("/", "-")
        return cls(
            run_id=run_id,
            test_id=test_id,
            test_name=test_name,
            config=config,
            start_time=now,
        )


@dataclass
class DiagnosticCollector:
    """Collects diagnostic information during test execution.

    Features:
    - Collects entries from all layers
    - Logs to files in test-logs/DATE_TIME/TEST_ID/PHASE.txt
    - Generates HTML reports
    - Shows diagnostics on error or in verbose mode

    Usage:
        collector = DiagnosticCollector(verbose=True)
        collector.set_context(test_name="010-flask", config="docker")

        collector.add_success("docker", "setup", "start_container", "Container started")
        collector.add_failure("server", "health_check", "http_check", "Server not responding",
                             stdout="...", stderr="...")

        # On error or at end:
        collector.save_logs()
        if generate_html:
            collector.generate_html_report()
    """

    verbose: bool = False
    """Whether to print entries as they are added."""

    log_dir: Path = field(default_factory=lambda: Path("test-logs"))
    """Directory for diagnostic logs."""

    entries: list[DiagnosticEntry] = field(default_factory=list, init=False)
    """Collected diagnostic entries."""

    context: TestRunContext | None = field(default=None, init=False)
    """Current test run context."""

    _current_phase: str = field(default="unknown", init=False)
    """Current test phase."""

    def set_context(self, test_name: str, config: str = "docker") -> None:
        """Set the test run context."""
        self.context = TestRunContext.create(test_name, config)

    def set_phase(self, phase: str) -> None:
        """Set the current phase."""
        self._current_phase = phase

    def _now(self) -> str:
        """Get current timestamp."""
        return datetime.now(tz=timezone.utc).isoformat()

    def add(self, entry: DiagnosticEntry) -> None:
        """Add a diagnostic entry."""
        self.entries.append(entry)
        if self.verbose:
            print(f"  {entry}")

    def add_success(
        self,
        layer: str,
        operation: str,
        message: str,
        phase: str | None = None,
        **kwargs,
    ) -> None:
        """Add a successful operation."""
        self.add(
            DiagnosticEntry(
                timestamp=self._now(),
                layer=layer,
                phase=phase or self._current_phase,
                operation=operation,
                success=True,
                message=message,
                **kwargs,
            )
        )

    def add_failure(
        self,
        layer: str,
        operation: str,
        message: str,
        phase: str | None = None,
        **kwargs,
    ) -> None:
        """Add a failed operation."""
        self.add(
            DiagnosticEntry(
                timestamp=self._now(),
                layer=layer,
                phase=phase or self._current_phase,
                operation=operation,
                success=False,
                message=message,
                **kwargs,
            )
        )

    def add_debug(
        self,
        layer: str,
        operation: str,
        message: str,
        phase: str | None = None,
        **kwargs,
    ) -> None:
        """Add debug information (always marked as success).

        Use for capturing diagnostic data like logs, configs, etc.
        that should be preserved in reports for debugging.
        """
        self.add(
            DiagnosticEntry(
                timestamp=self._now(),
                layer=layer,
                phase=phase or self._current_phase,
                operation=operation,
                success=True,
                message=message,
                **kwargs,
            )
        )

    def has_failures(self) -> bool:
        """Check if there are any failures."""
        return any(not e.success for e in self.entries)

    def get_failures(self) -> list[DiagnosticEntry]:
        """Get all failure entries."""
        return [e for e in self.entries if not e.success]

    def get_entries_by_phase(self, phase: str) -> list[DiagnosticEntry]:
        """Get entries for a specific phase."""
        return [e for e in self.entries if e.phase == phase]

    def get_entries_by_layer(self, layer: str) -> list[DiagnosticEntry]:
        """Get entries for a specific layer."""
        return [e for e in self.entries if e.layer == layer]

    def _format_entry(self, entry: DiagnosticEntry) -> list[str]:
        """Format a single diagnostic entry for console output."""
        lines = [str(entry)]
        if entry.duration > 0:
            lines.append(f"    duration: {entry.duration:.2f}s")
        if entry.details:
            for key, value in entry.details.items():
                lines.append(f"    {key}: {value}")
        if entry.stdout:
            lines.append("    stdout:")
            for line in entry.stdout.strip().split("\n")[:20]:
                lines.append(f"      {line}")
            if entry.stdout.count("\n") > 20:
                lines.append("      ... (truncated)")
        if entry.stderr:
            lines.append("    stderr:")
            for line in entry.stderr.strip().split("\n")[:20]:
                lines.append(f"      {line}")
            if entry.stderr.count("\n") > 20:
                lines.append("      ... (truncated)")
        return lines

    def dump_to_console(self, include_all: bool = False) -> str:
        """Format diagnostics for console output.

        Args:
            include_all: If True, show all entries. Otherwise only failures.

        Returns:
            Formatted diagnostic output
        """
        lines = ["", "=" * 70, "DIAGNOSTIC INFORMATION", "=" * 70]

        if self.context:
            lines.append(f"Test: {self.context.test_name}")
            lines.append(f"Config: {self.context.config}")
            lines.append(f"Run ID: {self.context.run_id}")
            lines.append("")

        entries = self.entries if include_all else self.get_failures()

        if not entries:
            lines.append(
                "No diagnostic entries recorded."
                if include_all
                else "No failures recorded."
            )
            lines.append("=" * 70)
            return "\n".join(lines)

        # Group by phase
        for phase in sorted({e.phase for e in entries}):
            phase_entries = [e for e in entries if e.phase == phase]
            lines.append(f"\n--- Phase: {phase} ---")
            for entry in phase_entries:
                lines.extend(self._format_entry(entry))

        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def _get_log_dir(self) -> Path:
        """Get the log directory for this test run."""
        if not self.context:
            # Fallback if no context set
            run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            test_id = "unknown"
        else:
            run_id = self.context.run_id
            test_id = self.context.test_id

        return self.log_dir / run_id / test_id

    def save_logs(self) -> Path:
        """Save diagnostic logs to files.

        Creates:
            test-logs/DATE_TIME/TEST_ID/
                summary.txt      - Overview of all phases
                PHASE.txt        - Detailed log for each phase
                entries.json     - Machine-readable log

        Returns:
            Path to the log directory
        """
        log_dir = self._get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)

        # Summary file
        summary_path = log_dir / "summary.txt"
        summary_path.write_text(self.dump_to_console(include_all=True))

        # Per-phase files
        phases = sorted({e.phase for e in self.entries})
        for phase in phases:
            phase_entries = self.get_entries_by_phase(phase)
            phase_path = log_dir / f"{phase}.txt"

            lines = [f"Phase: {phase}", "=" * 50, ""]
            for entry in phase_entries:
                lines.append(str(entry))
                lines.append(f"  Timestamp: {entry.timestamp}")
                lines.append(f"  Duration: {entry.duration:.2f}s")
                if entry.details:
                    lines.append("  Details:")
                    for key, value in entry.details.items():
                        lines.append(f"    {key}: {value}")
                if entry.stdout:
                    lines.append("  STDOUT:")
                    lines.append(entry.stdout)
                if entry.stderr:
                    lines.append("  STDERR:")
                    lines.append(entry.stderr)
                lines.append("")

            phase_path.write_text("\n".join(lines))

        # JSON file for machine parsing
        json_path = log_dir / "entries.json"
        json_data = {
            "context": asdict(self.context) if self.context else None,
            "entries": [e.to_dict() for e in self.entries],
        }
        json_path.write_text(json.dumps(json_data, indent=2, default=str))

        return log_dir

    def generate_html_report(self, output_path: Path | None = None) -> Path:
        """Generate an HTML report.

        Args:
            output_path: Where to save the report. If None, saves to log dir.

        Returns:
            Path to the generated report
        """
        if output_path is None:
            output_path = self._get_log_dir() / "report.html"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate HTML
        html_content = self._generate_html()
        output_path.write_text(html_content)

        return output_path

    def _generate_html(self) -> str:
        """Generate HTML report content."""
        ctx = self.context

        # Count stats
        total = len(self.entries)
        passed = sum(1 for e in self.entries if e.success)
        failed = total - passed

        # Group by phase
        phases = sorted({e.phase for e in self.entries})

        phase_sections = []
        for phase in phases:
            entries = self.get_entries_by_phase(phase)
            phase_passed = sum(1 for e in entries if e.success)
            phase_failed = len(entries) - phase_passed

            entry_rows = []
            for entry in entries:
                status_class = "success" if entry.success else "failure"
                status_icon = "\u2713" if entry.success else "\u2717"

                details_html = ""
                if entry.details:
                    details_items = "".join(
                        f"<li><strong>{html.escape(str(k))}:</strong> {html.escape(str(v))}</li>"
                        for k, v in entry.details.items()
                    )
                    details_html = f"<ul class='details'>{details_items}</ul>"

                stdout_html = ""
                if entry.stdout:
                    stdout_html = (
                        f"<pre class='stdout'>{html.escape(entry.stdout[:2000])}</pre>"
                    )

                stderr_html = ""
                if entry.stderr:
                    stderr_html = (
                        f"<pre class='stderr'>{html.escape(entry.stderr[:2000])}</pre>"
                    )

                entry_rows.append(f"""
                <tr class="{status_class}">
                    <td class="status">{status_icon}</td>
                    <td>{html.escape(entry.layer)}</td>
                    <td>{html.escape(entry.operation)}</td>
                    <td>{html.escape(entry.message)}</td>
                    <td>{entry.duration:.2f}s</td>
                </tr>
                {"<tr><td colspan='5'>" + details_html + stdout_html + stderr_html + "</td></tr>" if details_html or stdout_html or stderr_html else ""}
                """)

            phase_status = "phase-success" if phase_failed == 0 else "phase-failure"
            phase_sections.append(f"""
            <div class="phase {phase_status}">
                <h2>{html.escape(phase)} ({phase_passed}/{len(entries)} passed)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Layer</th>
                            <th>Operation</th>
                            <th>Message</th>
                            <th>Duration</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(entry_rows)}
                    </tbody>
                </table>
            </div>
            """)

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Hop3 Test Report - {html.escape(ctx.test_name if ctx else "Unknown")}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: #1a1a2e;
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .header h1 {{ margin: 0; }}
        .stats {{
            display: flex;
            gap: 20px;
            margin-top: 15px;
        }}
        .stat {{
            background: rgba(255,255,255,0.1);
            padding: 10px 20px;
            border-radius: 4px;
        }}
        .stat.passed {{ border-left: 4px solid #4caf50; }}
        .stat.failed {{ border-left: 4px solid #f44336; }}
        .phase {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .phase h2 {{
            margin-top: 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }}
        .phase-success h2 {{ border-color: #4caf50; }}
        .phase-failure h2 {{ border-color: #f44336; }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            text-align: left;
            padding: 10px;
            border-bottom: 1px solid #eee;
        }}
        th {{ background: #f9f9f9; }}
        tr.success .status {{ color: #4caf50; }}
        tr.failure {{ background: #fff5f5; }}
        tr.failure .status {{ color: #f44336; }}
        pre {{
            background: #1a1a2e;
            color: #eee;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 12px;
        }}
        pre.stderr {{ background: #2e1a1a; }}
        .details {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .details li {{ margin: 5px 0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Hop3 Test Report</h1>
        <div class="meta">
            <p>Test: <strong>{html.escape(ctx.test_name if ctx else "Unknown")}</strong></p>
            <p>Config: {html.escape(ctx.config if ctx else "Unknown")} | Run ID: {html.escape(ctx.run_id if ctx else "Unknown")}</p>
        </div>
        <div class="stats">
            <div class="stat passed">Passed: {passed}</div>
            <div class="stat failed">Failed: {failed}</div>
            <div class="stat">Total: {total}</div>
        </div>
    </div>

    {"".join(phase_sections)}

    <footer style="text-align: center; color: #666; margin-top: 40px;">
        Generated by hop3-testing at {datetime.now(tz=timezone.utc).isoformat()}
    </footer>
</body>
</html>
"""
