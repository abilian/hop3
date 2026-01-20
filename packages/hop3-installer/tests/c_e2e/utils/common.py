# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common utilities for E2E tests.

Provides logging functions and shared constants for test backends.
"""

from __future__ import annotations

import sys

from hop3_installer.common import Colors, CommandResult

__all__ = [
    "Colors",
    "CommandResult",
    "DRY_RUN",
    "VERBOSE",
    "log_debug",
    "log_error",
    "log_header",
    "log_info",
    "log_subheader",
    "log_success",
    "log_warning",
    "set_dry_run",
    "set_verbose",
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
# Logging Functions
# =============================================================================


def log_info(message: str) -> None:
    """Print an info message."""
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {message}")


def log_success(message: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}[PASS]{Colors.RESET} {message}")


def log_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {message}")


def log_error(message: str) -> None:
    """Print an error message."""
    print(f"{Colors.RED}[FAIL]{Colors.RESET} {message}", file=sys.stderr)


def log_debug(message: str) -> None:
    """Print a debug message (only in verbose mode)."""
    if VERBOSE:
        print(f"{Colors.DIM}[DEBUG]{Colors.RESET} {message}")


def log_header(message: str) -> None:
    """Print a section header."""
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {message}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.RESET}")
    print()


def log_subheader(message: str) -> None:
    """Print a subsection header."""
    print()
    print(f"{Colors.BOLD}--- {message} ---{Colors.RESET}")
    print()
