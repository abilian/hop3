# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Terminal output helpers for demos.

Uses termcolor for proper TTY detection - colors are only output when
stdout is a real terminal, not when piped to a file or another program.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from termcolor import colored

if TYPE_CHECKING:
    from lib.context import OutputLevel

# Global output level (can be set by demo.py)
_output_level: int = 2  # NORMAL


# =============================================================================
# Color helper functions that use termcolor (TTY-aware)
# These can be imported and used by other modules
# =============================================================================


def cyan(text: str) -> str:
    """Return cyan colored text (TTY-aware)."""
    return colored(text, "cyan")


def green(text: str) -> str:
    """Return green colored text (TTY-aware)."""
    return colored(text, "green")


def yellow(text: str) -> str:
    """Return yellow colored text (TTY-aware)."""
    return colored(text, "yellow")


def red(text: str) -> str:
    """Return red colored text (TTY-aware)."""
    return colored(text, "red")


def bold(text: str) -> str:
    """Return bold text (TTY-aware)."""
    return colored(text, attrs=["bold"])


def dim(text: str) -> str:
    """Return dimmed text (TTY-aware)."""
    return colored(text, attrs=["dark"])


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


def print_header(title: str, *, phase: bool = False) -> None:
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
    border = "=" * width
    print()
    print(cyan(bold(f"+{border}+")))
    print(cyan(bold(f"|  {title:<{width - 2}}|")))
    print(cyan(bold(f"+{border}+")))
    print()


def print_phase_result(*, success: bool) -> None:
    """Print phase result in quiet mode."""
    if _output_level == 1:  # QUIET
        if success:
            print(green("OK"))
        else:
            print(red("FAIL"))


def print_step(message: str) -> None:
    """Print a step description."""
    if _output_level < 2:  # SILENT or QUIET
        return
    print(f"{yellow('->')} {message}")


def print_command(cmd: str) -> None:
    """Print a command that will be executed."""
    if _output_level < 2:  # SILENT or QUIET
        return
    print()
    print(f"  {dim('$')} {bold(cmd)}")
    print()


def print_success(message: str) -> None:
    """Print a success message."""
    if _output_level < 2:  # SILENT or QUIET
        return
    print(f"{green('[OK]')} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    if _output_level == 0:  # SILENT
        print(f"Error: {message}")
        return

    print(f"{red('[ERROR]')} {message}")


def print_info(message: str) -> None:
    """Print an informational message."""
    if _output_level < 2:  # SILENT or QUIET
        return
    print(f"  {dim(message)}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    if _output_level == 0:  # SILENT
        return
    print(f"{yellow('[WARN]')} {message}")


def pause(seconds: float = 1.0) -> None:
    """Pause for screencast narration."""
    if _output_level < 2:  # SILENT or QUIET - no pauses
        return
    from lib.logging import record_timing

    time.sleep(seconds)
    record_timing(f"pause {seconds}s", seconds, category="pause")


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
            print(f"Error: {name} failed - {error}")
        return

    duration_str = format_duration(duration)

    if status == "pass":
        status_str = green("PASS")
    elif status == "fail":
        status_str = red("FAIL")
    else:  # skip
        status_str = yellow("SKIP")

    if _output_level == 1:  # QUIET
        if error:
            print(f"[{status_str}] {name} ({duration_str}) - {error}")
        else:
            print(f"[{status_str}] {name} ({duration_str})")
        return

    # NORMAL or VERBOSE
    print(f"  [{status_str}] {name} - {title:<35} ({duration_str})")
    if error:
        print(f"         +-- Error: {error}")


def print_summary_line() -> None:
    """Print a horizontal line for summary section."""
    if _output_level < 2:
        return
    print("-" * 69)


def print_summary_stats(
    passed: int, failed: int, skipped: int, total_duration: float
) -> None:
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
        parts.append(green(f"{passed} passed"))
    if failed > 0:
        parts.append(red(f"{failed} failed"))
    if skipped > 0:
        parts.append(yellow(f"{skipped} skipped"))

    print(f"Results: {', '.join(parts)}")
    print(f"Duration: {duration_str}")
