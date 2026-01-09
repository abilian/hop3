# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common utilities shared between CLI and server installers.

This module contains:
- Terminal output utilities (colors, printing)
- Spinner for long-running operations
- Command execution helpers
- System detection utilities

All code uses only the Python standard library.
"""

from __future__ import annotations

import itertools
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import overload

from typing_extensions import Self

# =============================================================================
# Terminal Colors
# =============================================================================


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"

    @classmethod
    def disable(cls) -> None:
        """Disable all colors (for non-TTY output)."""
        for attr in ["RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE", "CYAN"]:
            setattr(cls, attr, "")


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


# =============================================================================
# Output Functions
# =============================================================================


def print_header(title: str) -> None:
    """Print a styled header."""
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}{title}{Colors.RESET}")
    print(f"{Colors.DIM}{'=' * len(title)}{Colors.RESET}")
    print()


def print_step(step: int, total: int, message: str) -> None:
    """Print a step indicator."""
    print(f"\n{Colors.BOLD}[{step}/{total}]{Colors.RESET} {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"      {Colors.GREEN}✓{Colors.RESET} {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"      {Colors.BLUE}ℹ{Colors.RESET} {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"      {Colors.YELLOW}⚠{Colors.RESET} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"      {Colors.RED}✗{Colors.RESET} {message}", file=sys.stderr)


def print_detail(message: str) -> None:
    """Print a detail/sub-item."""
    print(f"        {Colors.DIM}{message}{Colors.RESET}")


# =============================================================================
# Spinner for Long Operations
# =============================================================================


class Spinner:
    """A simple terminal spinner for long-running operations.

    Usage:
        with Spinner("Installing packages..."):
            # long operation
            pass
    """

    CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str):
        self.message = message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Self:
        if sys.stdout.isatty():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        else:
            print(f"      ... {self.message}")
        return self

    def __exit__(self, *args) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        if sys.stdout.isatty():
            # Clear the spinner line
            print(f"\r{' ' * (len(self.message) + 12)}\r", end="")

    def _spin(self) -> None:
        for char in itertools.cycle(self.CHARS):
            if self._stop_event.is_set():
                break
            print(
                f"\r      {Colors.CYAN}{char}{Colors.RESET} {self.message}",
                end="",
                flush=True,
            )
            time.sleep(0.08)


# =============================================================================
# Command Execution
# =============================================================================


@dataclass
class CommandResult:
    """Result of a command execution."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def success(self) -> bool:
        """Check if the command succeeded."""
        return self.returncode == 0


@dataclass
class CommandError(Exception):
    """Raised when a command fails."""

    cmd: list[str]
    returncode: int
    stderr: str
    stdout: str = ""

    def __str__(self) -> str:
        return f"Command failed: {' '.join(self.cmd)}"


def run_cmd(
    cmd: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """Run a command and return the result.

    Args:
        cmd: Command and arguments to run
        capture: Whether to capture stdout/stderr
        check: Whether to raise CommandError on non-zero exit
        env: Additional environment variables
        timeout: Timeout in seconds (None for no timeout)

    Returns:
        CompletedProcess with returncode, stdout, stderr

    Raises:
        CommandError: If check=True and command returns non-zero
    """
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=capture,
            text=True,
            env=run_env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # Return a failed result on timeout
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=-1,
            stdout="",
            stderr="Command timed out",
        )

    if check and result.returncode != 0:
        raise CommandError(
            cmd=cmd,
            returncode=result.returncode,
            stderr=result.stderr or "",
            stdout=result.stdout or "",
        )

    return result


def cmd_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None


# =============================================================================
# System Detection
# =============================================================================


def detect_distro() -> str:
    """Detect the Linux distribution.

    Returns:
        'debian' for Debian-based distros (Ubuntu, Mint, Pop!_OS)
        'fedora' for Red Hat-based distros (Fedora, RHEL, CentOS, Rocky, Alma)
        'arch' for Arch Linux
        'unknown' for unrecognized distributions
    """
    os_release = Path("/etc/os-release")
    if os_release.exists():
        content = os_release.read_text().lower()
        if any(d in content for d in ["ubuntu", "debian", "mint", "pop"]):
            return "debian"
        if any(d in content for d in ["fedora", "rhel", "centos", "rocky", "alma"]):
            return "fedora"
        if "arch" in content:
            return "arch"
    return "unknown"


def get_current_shell() -> str | None:
    """Detect the current shell.

    Returns:
        'bash', 'zsh', 'fish', or None if unrecognized
    """
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return "zsh"
    if "fish" in shell:
        return "fish"
    if "bash" in shell:
        return "bash"
    return None


# =============================================================================
# Version Check Helper
# =============================================================================


MIN_PYTHON = (3, 10)


def find_project_root(start_path: Path | None = None) -> Path:
    """Find the project root directory.

    Walks up from the starting path looking for pyproject.toml and packages/ directory.

    Args:
        start_path: Path to start searching from. If None, uses current working directory.

    Returns:
        Path to project root, or current working directory if not found.
    """
    current = start_path or Path.cwd()

    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "packages").exists():
            return parent
        if (parent / ".git").exists() and (parent / "packages").exists():
            return parent

    return Path.cwd()


def check_python_version() -> None:
    """Check that Python version meets minimum requirements.

    Exits with error message if Python version is too old.
    """
    if sys.version_info < MIN_PYTHON:
        print(f"Error: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required")
        print(f"Found: Python {sys.version_info.major}.{sys.version_info.minor}")
        print()
        print("Please install a newer Python version:")
        print("  Ubuntu/Debian: sudo apt install python3.11")
        print("  Fedora:        sudo dnf install python3.11")
        print("  macOS:         brew install python@3.11")
        sys.exit(1)


# =============================================================================
# Environment Variable Helpers
# =============================================================================


@overload
def env_str(name: str) -> str | None: ...


@overload
def env_str(name: str, default: str) -> str: ...


def env_str(name: str, default: str | None = None) -> str | None:
    """Get a string environment variable.

    Args:
        name: Environment variable name.
        default: Default value if not set.

    Returns:
        The environment variable value, or default if not set.
        When default is a str, return type is str.
        When default is None (or omitted), return type is str | None.
    """
    return os.environ.get(name, default)


def env_bool(name: str) -> bool:
    """Get a boolean environment variable.

    Recognizes "1" and "true" (case-insensitive) as True.

    Args:
        name: Environment variable name.

    Returns:
        True if set to "1" or "true", False otherwise.
    """
    return os.environ.get(name, "").lower() in {"1", "true"}


def env_path(name: str, default: Path) -> Path:
    """Get a Path environment variable.

    Args:
        name: Environment variable name.
        default: Default Path if not set.

    Returns:
        Path from environment variable, or default.
    """
    value = os.environ.get(name)
    return Path(value) if value else default


def env_list(name: str, separator: str = ",") -> list[str]:
    """Get a list from a separated environment variable.

    Args:
        name: Environment variable name.
        separator: Separator character (default: comma).

    Returns:
        List of stripped, non-empty values.
    """
    value = os.environ.get(name, "")
    return [item.strip() for item in value.split(separator) if item.strip()]
