# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Logging infrastructure for demo runner.

Provides file-based logging for debugging demo failures:
- Timestamped log directories: demos/logs/YYYY-MM-DD-HH-mm/
- Per-demo subdirectories: demo42/main.txt, demo42/docker-build.txt, etc.
- Captures command output, docker logs, and errors
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

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
