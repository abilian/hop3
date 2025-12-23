# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common utilities for installer testing."""

from __future__ import annotations

import sys
from dataclasses import dataclass

# =============================================================================
# Global State
# =============================================================================

VERBOSE = False
DRY_RUN = False


def set_verbose(value: bool) -> None:
    """Set verbose mode globally."""
    global VERBOSE
    VERBOSE = value


def set_dry_run(value: bool) -> None:
    """Set dry-run mode globally."""
    global DRY_RUN
    DRY_RUN = value


# =============================================================================
# Command Result
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


# =============================================================================
# Terminal Colors
# =============================================================================


@dataclass
class Colors:
    """ANSI color codes for terminal output."""

    RESET: str = "\033[0m"
    RED: str = "\033[0;31m"
    GREEN: str = "\033[0;32m"
    YELLOW: str = "\033[0;33m"
    BLUE: str = "\033[0;34m"
    MAGENTA: str = "\033[0;35m"
    CYAN: str = "\033[0;36m"
    BOLD: str = "\033[1m"
    DIM: str = "\033[2m"

    @classmethod
    def disabled(cls) -> Colors:
        """Return a Colors instance with all colors disabled."""
        return cls(
            RESET="",
            RED="",
            GREEN="",
            YELLOW="",
            BLUE="",
            MAGENTA="",
            CYAN="",
            BOLD="",
            DIM="",
        )


# Global colors instance - disabled if not a TTY
C = Colors() if sys.stdout.isatty() else Colors.disabled()


# =============================================================================
# Logging Functions
# =============================================================================


def log_info(message: str) -> None:
    """Print an info message."""
    print(f"{C.BLUE}[INFO]{C.RESET} {message}")


def log_success(message: str) -> None:
    """Print a success message."""
    print(f"{C.GREEN}[PASS]{C.RESET} {message}")


def log_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{C.YELLOW}[WARN]{C.RESET} {message}")


def log_error(message: str) -> None:
    """Print an error message."""
    print(f"{C.RED}[FAIL]{C.RESET} {message}", file=sys.stderr)


def log_debug(message: str) -> None:
    """Print a debug message (only in verbose mode)."""
    if VERBOSE:
        print(f"{C.DIM}[DEBUG]{C.RESET} {message}")


def log_header(message: str) -> None:
    """Print a section header."""
    print()
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {message}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print()


def log_subheader(message: str) -> None:
    """Print a subsection header."""
    print()
    print(f"{C.BOLD}--- {message} ---{C.RESET}")
    print()
