# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common utilities for installer testing."""

from __future__ import annotations

import sys

from hop3_installer.common import Colors, CommandResult

# Re-export for backwards compatibility
__all__ = [
    "CommandResult",
    "Colors",
    "VERBOSE",
    "DRY_RUN",
    "set_verbose",
    "set_dry_run",
    "log_info",
    "log_success",
    "log_warning",
    "log_error",
    "log_debug",
    "log_header",
    "log_subheader",
]

# =============================================================================
# Global State
# =============================================================================

VERBOSE = False
DRY_RUN = False


def set_verbose(*, value: bool) -> None:
    """Set verbose mode globally."""
    global VERBOSE
    VERBOSE = value


def set_dry_run(*, value: bool) -> None:
    """Set dry-run mode globally."""
    global DRY_RUN
    DRY_RUN = value


# =============================================================================
# Terminal Colors
# =============================================================================

# Alias for Colors class - allows using C.RED, C.BLUE etc. in log functions
# The Colors class from common.py uses class attributes, so C.BLUE works directly
C = Colors


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
