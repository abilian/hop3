# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Interactive prompts for CLI."""

from __future__ import annotations

import sys


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

    Used for critical destructive operations like app:destroy.

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
