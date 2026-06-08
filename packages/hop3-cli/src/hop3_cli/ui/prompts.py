# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Interactive prompts for CLI."""

from __future__ import annotations

import os
import sys


class NoInputError(Exception):
    """Raised when an interactive prompt is reached but --no-input was set.

    Per ADR 036 G5, ``--no-input`` refuses to prompt and fails fast with an
    actionable hint instead of silently hanging or assuming a default.
    Callers catch this and emit a context-specific message about the flag
    or env var to use to non-interactively supply the missing value.
    """


def is_no_input() -> bool:
    """Whether --no-input was set (env-var bridged from parse_flags)."""
    return os.environ.get("HOP3_NO_INPUT", "") == "1"


def require_input_allowed(prompt_label: str) -> None:
    """Raise NoInputError if interactive input has been disabled.

    Local prompt sites call this at the top of their flow so the script
    stops with an explanatory error before printing a prompt that nothing
    will answer.
    """
    if is_no_input():
        msg = (
            f"{prompt_label} would require an interactive prompt, "
            f"but --no-input was passed. Provide the value via the "
            f"appropriate flag or environment variable."
        )
        raise NoInputError(msg)


def confirm(message: str, *, default: bool = False) -> bool:
    """Ask user for yes/no confirmation.

    Args:
        message: The confirmation message
        default: Default value if user just presses Enter

    Returns:
        True if user confirmed, False otherwise

    Examples:
        >>> if confirm("Delete this file?"):
        ...     delete_file()
    """
    prompt = f"{message} [y/N]: " if not default else f"{message} [Y/n]: "

    try:
        response = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        # User pressed Ctrl+C or Ctrl+D
        print("\nAborted.", file=sys.stderr)
        return False

    if not response:
        return default

    return response in {"y", "yes"}


def type_to_confirm(message: str, required_text: str) -> bool:
    """Require user to type specific text to confirm.

    Used for critical destructive operations like app destroy.

    Args:
        message: The confirmation message explaining what will be typed
        required_text: The exact text user must type

    Returns:
        True if user typed correct text, False otherwise

    Examples:
        >>> if type_to_confirm("Type 'my-app' to destroy it:", "my-app"):
        ...     destroy_app()
    """
    try:
        response = input(f"{message} ").strip()
    except (EOFError, KeyboardInterrupt):
        # User pressed Ctrl+C or Ctrl+D
        print("\nAborted.", file=sys.stderr)
        return False

    if response == required_text:
        return True

    print(f"Incorrect. Expected '{required_text}', got '{response}'.", file=sys.stderr)
    print("Aborted.", file=sys.stderr)
    return False


def show_destructive_warning(command: str, target: str, details: str = "") -> None:
    """Display a warning message before destructive action.

    Args:
        command: The command being executed (e.g., "destroy", "delete")
        target: What is being destroyed/deleted (e.g., "app 'my-app'", "backup")
        details: Additional details about what will be lost
    """
    print(file=sys.stderr)
    print("⚠  WARNING: DESTRUCTIVE ACTION", file=sys.stderr)
    print(file=sys.stderr)
    print(f"   This will permanently {command} {target}.", file=sys.stderr)

    if details:
        print(f"   {details}", file=sys.stderr)

    print(file=sys.stderr)
    print("   This action CANNOT be undone!", file=sys.stderr)
    print(file=sys.stderr)
