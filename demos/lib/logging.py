# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Logging infrastructure for demo runner.

Provides file-based logging for debugging demo failures:
- Timestamped log directories: demos/logs/YYYY-MM-DD-HH-mm/
- Per-demo subdirectories: demo42/main.txt, demo42/docker-build.txt, etc.
- Captures command output, docker logs, and errors
- Timing instrumentation for performance analysis
"""

from __future__ import annotations

import subprocess
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from .context import DemoContext

# Default logs directory relative to demos/
DEFAULT_LOGS_DIR = Path(__file__).parent.parent / "logs"


@dataclass
class LogSession:
    """Manages logging for a demo run session."""

    base_dir: Path
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d-%H-%M"))
    _current_demo: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Create the session log directory."""
        self.session_dir.mkdir(parents=True, exist_ok=True)

    @property
    def session_dir(self) -> Path:
        """Return the timestamped session directory."""
        return self.base_dir / self.timestamp

    @property
    def current_demo_dir(self) -> Path | None:
        """Return the current demo's log directory."""
        if self._current_demo is None:
            return None
        return self.session_dir / self._current_demo

    def start_demo(self, demo_name: str) -> Path:
        """Start logging for a new demo, creating its directory."""
        self._current_demo = demo_name
        demo_dir = self.session_dir / demo_name
        demo_dir.mkdir(parents=True, exist_ok=True)
        return demo_dir

    def end_demo(self) -> None:
        """End logging for the current demo."""
        self._current_demo = None

    def log_file(self, name: str, demo_name: str | None = None) -> Path:
        """Get the path to a log file.

        Args:
            name: Log file name (e.g., "main", "docker-build", "container-logs")
            demo_name: Demo name (uses current demo if None)

        Returns:
            Path to the log file (creates parent directory if needed)
        """
        demo = demo_name or self._current_demo
        if demo:
            log_dir = self.session_dir / demo
        else:
            log_dir = self.session_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"{name}.txt"

    def write(self, name: str, content: str, demo_name: str | None = None) -> None:
        """Write content to a log file.

        Args:
            name: Log file name (without .txt extension)
            content: Content to write
            demo_name: Demo name (uses current demo if None)
        """
        log_path = self.log_file(name, demo_name)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")

    def write_command(
        self,
        name: str,
        command: str,
        result: subprocess.CompletedProcess,
        demo_name: str | None = None,
    ) -> None:
        """Write command execution details to a log file.

        Args:
            name: Log file name
            command: Command that was executed
            result: CompletedProcess from subprocess.run
            demo_name: Demo name (uses current demo if None)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content = f"""
{'=' * 80}
[{timestamp}] Command: {command}
Exit code: {result.returncode}
{'=' * 80}

--- STDOUT ---
{result.stdout or '(empty)'}

--- STDERR ---
{result.stderr or '(empty)'}

"""
        self.write(name, content, demo_name)

    def write_section(
        self,
        name: str,
        section_title: str,
        content: str,
        demo_name: str | None = None,
    ) -> None:
        """Write a titled section to a log file.

        Args:
            name: Log file name
            section_title: Title for this section
            content: Section content
            demo_name: Demo name (uses current demo if None)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        section = f"""
{'=' * 80}
[{timestamp}] {section_title}
{'=' * 80}

{content}

"""
        self.write(name, section, demo_name)


# Global log session (initialized by demo.py)
_log_session: LogSession | None = None


def init_logging(base_dir: Path | None = None) -> LogSession:
    """Initialize the global log session.

    Args:
        base_dir: Base directory for logs (defaults to demos/logs/)

    Returns:
        The initialized LogSession
    """
    global _log_session
    _log_session = LogSession(base_dir=base_dir or DEFAULT_LOGS_DIR)
    return _log_session


def get_log_session() -> LogSession | None:
    """Get the current log session."""
    return _log_session


def log_command(
    name: str,
    command: str,
    result: subprocess.CompletedProcess,
    demo_name: str | None = None,
) -> None:
    """Log a command execution to the current session.

    Args:
        name: Log file name
        command: Command that was executed
        result: CompletedProcess from subprocess.run
        demo_name: Demo name (uses current demo if None)
    """
    if _log_session:
        _log_session.write_command(name, command, result, demo_name)


def log_section(
    name: str,
    section_title: str,
    content: str,
    demo_name: str | None = None,
) -> None:
    """Log a titled section to the current session.

    Args:
        name: Log file name
        section_title: Title for this section
        content: Section content
        demo_name: Demo name (uses current demo if None)
    """
    if _log_session:
        _log_session.write_section(name, section_title, content, demo_name)


def log_text(name: str, content: str, demo_name: str | None = None) -> None:
    """Log raw text to the current session.

    Args:
        name: Log file name
        content: Content to write
        demo_name: Demo name (uses current demo if None)
    """
    if _log_session:
        _log_session.write(name, content, demo_name)


def start_demo_logging(demo_name: str) -> Path | None:
    """Start logging for a demo.

    Args:
        demo_name: Name of the demo

    Returns:
        Path to the demo's log directory, or None if logging not initialized
    """
    if _log_session:
        return _log_session.start_demo(demo_name)
    return None


def end_demo_logging() -> None:
    """End logging for the current demo."""
    if _log_session:
        _log_session.end_demo()


def capture_docker_logs(ctx: DemoContext, app_name: str) -> str | None:
    """Capture Docker container logs for an app.

    Args:
        ctx: Demo context with server connection info
        app_name: Name of the application

    Returns:
        Container logs as string, or None on failure
    """
    from .commands import run_ssh

    # Get container ID
    result = run_ssh(
        ctx,
        f"docker ps -aq --filter name={app_name}",
        check=False,
        show=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        # Try with prefix matching
        result = run_ssh(
            ctx,
            f"docker ps -aq --filter 'name=^{app_name}'",
            check=False,
            show=False,
        )

    container_id = result.stdout.strip().split("\n")[0] if result.stdout else ""
    if not container_id:
        return None

    # Get container logs
    result = run_ssh(
        ctx,
        f"docker logs {container_id} 2>&1",
        check=False,
        show=False,
    )
    return result.stdout if result.returncode == 0 else None


def capture_docker_inspect(ctx: DemoContext, app_name: str) -> str | None:
    """Capture Docker container inspect output for an app.

    Args:
        ctx: Demo context with server connection info
        app_name: Name of the application

    Returns:
        Container inspect JSON, or None on failure
    """
    from .commands import run_ssh

    result = run_ssh(
        ctx,
        f"docker ps -aq --filter name={app_name}",
        check=False,
        show=False,
    )
    container_id = result.stdout.strip().split("\n")[0] if result.stdout else ""
    if not container_id:
        return None

    result = run_ssh(
        ctx,
        f"docker inspect {container_id}",
        check=False,
        show=False,
    )
    return result.stdout if result.returncode == 0 else None


def capture_failure_debug(ctx: DemoContext, app_name: str) -> None:
    """Capture all debugging information on failure.

    Collects container logs, inspect output, and app status.
    Writes to the current demo's log directory.

    Args:
        ctx: Demo context
        app_name: Name of the failed application
    """
    from .commands import run_hop3, run_ssh

    # Capture container logs
    logs = capture_docker_logs(ctx, app_name)
    if logs:
        log_section("container-logs", f"Docker logs for {app_name}", logs)

    # Capture container inspect
    inspect = capture_docker_inspect(ctx, app_name)
    if inspect:
        log_section("container-inspect", f"Docker inspect for {app_name}", inspect)

    # Capture app status
    result = run_hop3(f"apps:info {app_name}", check=False, show=False)
    if result.stdout:
        log_section("app-info", f"App info for {app_name}", result.stdout)

    # Capture server logs (last 100 lines)
    result = run_ssh(
        ctx,
        "journalctl -u hop3-server -n 100 --no-pager 2>/dev/null || tail -100 /var/log/hop3/server.log 2>/dev/null || echo 'No server logs found'",
        check=False,
        show=False,
    )
    if result.stdout:
        log_section("server-logs", "Hop3 server logs (last 100 lines)", result.stdout)


# =============================================================================
# Timing Infrastructure
# =============================================================================


@dataclass
class TimingRecord:
    """A single timing measurement."""

    label: str
    elapsed: float  # seconds
    category: str = "general"  # "demo", "deploy", "hop3", "wait", etc.
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DemoTimings:
    """Timing data for a single demo run."""

    demo_name: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    records: list[TimingRecord] = field(default_factory=list)

    @property
    def total_elapsed(self) -> float:
        """Total elapsed time for the demo."""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def add(self, label: str, elapsed: float, category: str = "general") -> None:
        """Add a timing record."""
        self.records.append(TimingRecord(label=label, elapsed=elapsed, category=category))

    def finish(self) -> None:
        """Mark the demo as finished."""
        self.end_time = time.time()

    def summary(self) -> str:
        """Generate a timing summary."""
        lines = [
            f"Timing Summary for {self.demo_name}",
            "=" * 60,
            f"Total time: {self.total_elapsed:.1f}s",
            "",
            "Breakdown by operation:",
        ]

        # Group by category
        by_category: dict[str, list[TimingRecord]] = defaultdict(list)
        for rec in self.records:
            by_category[rec.category].append(rec)

        for category, recs in sorted(by_category.items()):
            cat_total = sum(r.elapsed for r in recs)
            lines.append(f"\n  [{category}] ({cat_total:.1f}s total)")
            for rec in recs:
                pct = (rec.elapsed / self.total_elapsed * 100) if self.total_elapsed > 0 else 0
                lines.append(f"    - {rec.label}: {rec.elapsed:.1f}s ({pct:.0f}%)")

        # Unaccounted time
        accounted = sum(r.elapsed for r in self.records)
        unaccounted = self.total_elapsed - accounted
        if unaccounted > 0.5:  # Only show if > 0.5s
            lines.append(f"\n  [overhead/unaccounted]: {unaccounted:.1f}s")

        return "\n".join(lines)


class TimingCollector:
    """Collects timing data across demos for aggregate analysis."""

    def __init__(self) -> None:
        self.demos: list[DemoTimings] = []
        self._current: DemoTimings | None = None
        self.setup_timings: list[TimingRecord] = []  # Capture setup phase timing

    def start_demo(self, demo_name: str) -> DemoTimings:
        """Start timing a new demo."""
        self._current = DemoTimings(demo_name=demo_name)
        self.demos.append(self._current)
        return self._current

    def end_demo(self) -> DemoTimings | None:
        """End timing the current demo."""
        if self._current:
            self._current.finish()
            result = self._current
            self._current = None
            return result
        return None

    @property
    def current(self) -> DemoTimings | None:
        """Get the current demo timings."""
        return self._current

    def record(self, label: str, elapsed: float, category: str = "general") -> None:
        """Record a timing to the current demo or setup phase."""
        if self._current:
            self._current.add(label, elapsed, category)
        else:
            # No demo started yet - record to setup timings
            self.setup_timings.append(TimingRecord(label=label, elapsed=elapsed, category=category))

    def setup_summary(self) -> str:
        """Generate setup phase timing summary."""
        if not self.setup_timings:
            return ""

        lines = [
            "Setup Phase Timing",
            "=" * 60,
            f"Total setup time: {sum(r.elapsed for r in self.setup_timings):.1f}s",
            "",
            "Breakdown by operation:",
        ]

        # Group by category
        by_category: dict[str, list[TimingRecord]] = defaultdict(list)
        for rec in self.setup_timings:
            by_category[rec.category].append(rec)

        for category, records in sorted(by_category.items(), key=lambda x: -sum(r.elapsed for r in x[1])):
            cat_total = sum(r.elapsed for r in records)
            lines.append(f"\n  [{category}] ({cat_total:.1f}s total)")
            for rec in records:
                pct = (rec.elapsed / sum(r.elapsed for r in self.setup_timings)) * 100
                lines.append(f"    - {rec.label}: {rec.elapsed:.1f}s ({pct:.0f}%)")

        return "\n".join(lines)

    def aggregate_summary(self) -> str:
        """Generate aggregate timing summary across all demos."""
        if not self.demos and not self.setup_timings:
            return "No timing data collected."

        lines = []

        # Include setup timing if present
        if self.setup_timings:
            lines.append(self.setup_summary())
            lines.append("")

        if not self.demos:
            return "\n".join(lines) if lines else "No timing data collected."

        lines.extend([
            "Aggregate Timing Summary",
            "=" * 60,
            f"Total demos: {len(self.demos)}",
            f"Total time: {sum(d.total_elapsed for d in self.demos):.1f}s",
            f"Average per demo: {sum(d.total_elapsed for d in self.demos) / len(self.demos):.1f}s",
            "",
        ])

        # Aggregate by category across all demos
        by_category: dict[str, list[float]] = defaultdict(list)
        for demo in self.demos:
            for rec in demo.records:
                by_category[rec.category].append(rec.elapsed)

        lines.append("Average time by category:")
        for category, times in sorted(by_category.items(), key=lambda x: -sum(x[1])):
            avg = sum(times) / len(times) if times else 0
            total = sum(times)
            lines.append(f"  [{category}] avg: {avg:.1f}s, total: {total:.1f}s, count: {len(times)}")

        # Slowest demos
        lines.append("\nSlowest demos:")
        for demo in sorted(self.demos, key=lambda d: -d.total_elapsed)[:5]:
            lines.append(f"  - {demo.demo_name}: {demo.total_elapsed:.1f}s")

        return "\n".join(lines)


# Global timing collector
_timing_collector: TimingCollector | None = None


def init_timing() -> TimingCollector:
    """Initialize the global timing collector."""
    global _timing_collector
    _timing_collector = TimingCollector()
    return _timing_collector


def get_timing_collector() -> TimingCollector | None:
    """Get the global timing collector."""
    return _timing_collector


def start_demo_timing(demo_name: str) -> None:
    """Start timing a demo."""
    if _timing_collector:
        _timing_collector.start_demo(demo_name)


def end_demo_timing() -> str | None:
    """End timing the current demo and return summary."""
    if _timing_collector:
        demo = _timing_collector.end_demo()
        if demo:
            return demo.summary()
    return None


def record_timing(label: str, elapsed: float, category: str = "general") -> None:
    """Record a timing measurement."""
    if _timing_collector:
        _timing_collector.record(label, elapsed, category)


@contextmanager
def timed(label: str, category: str = "general", print_result: bool = False) -> Generator[None, None, None]:
    """Context manager to time an operation.

    Args:
        label: Description of the operation
        category: Category for grouping (deploy, hop3, wait, curl, etc.)
        print_result: If True, print timing to console

    Usage:
        with timed("deploy app", category="deploy"):
            run_hop3("deploy myapp")
    """
    start = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start
        record_timing(label, elapsed, category)
        if print_result:
            print(f"[TIMING] {label}: {elapsed:.1f}s")


def timed_call(label: str, category: str = "general"):
    """Decorator to time a function call.

    Usage:
        @timed_call("deploy_app", category="deploy")
        def deploy_app(ctx, app_name, app_dir):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with timed(label, category):
                return func(*args, **kwargs)
        return wrapper
    return decorator
