# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Terminal output helpers for demos."""

from __future__ import annotations

import time


class Colors:
    """ANSI color codes for terminal output."""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def print_header(title: str) -> None:
    """Print a prominent section header."""
    width = 68
    border = "═" * width
    print()
    print(f"{Colors.CYAN}{Colors.BOLD}╔{border}╗{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}║  {title:<{width - 2}}║{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}╚{border}╝{Colors.RESET}")
    print()


def print_step(message: str) -> None:
    """Print a step description."""
    print(f"{Colors.YELLOW}→{Colors.RESET} {message}")


def print_command(cmd: str) -> None:
    """Print a command that will be executed."""
    print()
    print(f"  {Colors.DIM}${Colors.RESET} {Colors.BOLD}{cmd}{Colors.RESET}")
    print()


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}✓{Colors.RESET} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{Colors.RED}✗{Colors.RESET} {message}")


def print_info(message: str) -> None:
    """Print an informational message."""
    print(f"  {Colors.DIM}{message}{Colors.RESET}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {message}")


def pause(seconds: float = 1.0) -> None:
    """Pause for screencast narration."""
    time.sleep(seconds)
