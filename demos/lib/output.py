# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Terminal output helpers for demos."""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.context import OutputLevel

# Global output level (can be set by demo.py)
_output_level: int = 2  # NORMAL


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


def set_output_level(level: OutputLevel | int) -> None:
    """Set the global output level."""
    global _output_level
    _output_level = int(level)


def get_output_level() -> int:
    """Get the current output level."""
    return _output_level


def should_output(min_level: int) -> bool:
    """Check if output should be shown at the current level."""
    return _output_level >= min_level


def print_header(title: str, phase: bool = False) -> None:
    """Print a prominent section header.

    Args:
        title: The header text
        phase: If True, this is a top-level phase (show in quiet mode)
    """
    if _output_level == 0:  # SILENT
        return
    if _output_level == 1:  # QUIET
        if phase:
            # Only show top-level phases in quiet mode
            print(f"{title}... ", end="", flush=True)
        return

    # NORMAL or VERBOSE
    width = 68
    border = "═" * width
    print()
    print(f"{Colors.CYAN}{Colors.BOLD}╔{border}╗{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}║  {title:<{width - 2}}║{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}╚{border}╝{Colors.RESET}")
    print()


def print_phase_result(success: bool) -> None:
    """Print phase result in quiet mode."""
    if _output_level == 1:  # QUIET
        if success:
            print(f"{Colors.GREEN}OK{Colors.RESET}")
        else:
            print(f"{Colors.RED}FAIL{Colors.RESET}")


def print_step(message: str) -> None:
    """Print a step description."""
    if _output_level < 2:  # SILENT or QUIET
        return
    print(f"{Colors.YELLOW}→{Colors.RESET} {message}")


def print_command(cmd: str) -> None:
    """Print a command that will be executed."""
    if _output_level < 2:  # SILENT or QUIET
        return
    print()
    print(f"  {Colors.DIM}${Colors.RESET} {Colors.BOLD}{cmd}{Colors.RESET}")
    print()


def print_success(message: str) -> None:
    """Print a success message."""
    if _output_level < 2:  # SILENT or QUIET
        return
    print(f"{Colors.GREEN}✓{Colors.RESET} {message}")


def print_error(message: str, to_stderr: bool = False) -> None:
    """Print an error message.

    In silent mode, errors always go to stderr.
    """
    if _output_level == 0:  # SILENT - errors to stderr
        print(f"Error: {message}", file=sys.stderr)
        return

    output = sys.stderr if to_stderr else sys.stdout
    print(f"{Colors.RED}✗{Colors.RESET} {message}", file=output)


def print_info(message: str) -> None:
    """Print an informational message."""
    if _output_level < 2:  # SILENT or QUIET
        return
    print(f"  {Colors.DIM}{message}{Colors.RESET}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    if _output_level == 0:  # SILENT
        return
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {message}")


def pause(seconds: float = 1.0) -> None:
    """Pause for screencast narration."""
    if _output_level < 2:  # SILENT or QUIET - no pauses
        return
    time.sleep(seconds)


def print_blank() -> None:
    """Print a blank line, respecting output level."""
    if _output_level < 2:  # SILENT or QUIET
        return
    print()


def format_duration(seconds: float) -> str:
    """Format duration in seconds to a readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def print_demo_result(
    name: str,
    title: str,
    status: str,
    duration: float,
    error: str | None = None,
) -> None:
    """Print a single demo result line."""
    if _output_level == 0:  # SILENT
        if status == "fail" and error:
            print(f"Error: {name} failed - {error}", file=sys.stderr)
        return

    duration_str = format_duration(duration)

    if status == "pass":
        status_str = f"{Colors.GREEN}PASS{Colors.RESET}"
    elif status == "fail":
        status_str = f"{Colors.RED}FAIL{Colors.RESET}"
    else:  # skip
        status_str = f"{Colors.YELLOW}SKIP{Colors.RESET}"

    if _output_level == 1:  # QUIET
        if error:
            print(f"[{status_str}] {name} ({duration_str}) - {error}")
        else:
            print(f"[{status_str}] {name} ({duration_str})")
        return

    # NORMAL or VERBOSE
    print(f"  [{status_str}] {name} - {title:<35} ({duration_str})")
    if error:
        print(f"         └─ Error: {error}")


def print_summary_line() -> None:
    """Print a horizontal line for summary section."""
    if _output_level < 2:
        return
    print("─" * 69)


def print_summary_stats(passed: int, failed: int, skipped: int, total_duration: float) -> None:
    """Print summary statistics."""
    if _output_level == 0:  # SILENT
        return

    total = passed + failed + skipped
    duration_str = format_duration(total_duration)

    if _output_level == 1:  # QUIET
        if failed > 0:
            print(f"\n{passed}/{total} passed ({duration_str})")
        else:
            print(f"\n{passed}/{total} passed ({duration_str})")
        return

    # NORMAL or VERBOSE
    print_summary_line()
    parts = []
    if passed > 0:
        parts.append(f"{Colors.GREEN}{passed} passed{Colors.RESET}")
    if failed > 0:
        parts.append(f"{Colors.RED}{failed} failed{Colors.RESET}")
    if skipped > 0:
        parts.append(f"{Colors.YELLOW}{skipped} skipped{Colors.RESET}")

    print(f"Results: {', '.join(parts)}")
    print(f"Duration: {duration_str}")
