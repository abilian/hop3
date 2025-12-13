# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Destructive command handling and confirmation prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_cli.ui.prompts import confirm, show_destructive_warning, type_to_confirm

if TYPE_CHECKING:
    from hop3_cli.ui.rich_printer import RichPrinter


def is_destructive_command(cli_args: list[str]) -> bool:
    """Check if the command is destructive (requires confirmation).

    Args:
        cli_args: Command-line arguments

    Returns:
        True if command is destructive, False otherwise
    """
    if not cli_args:
        return False

    command = cli_args[0]

    # List of destructive commands that require confirmation
    destructive_commands = {
        "app:destroy",
        "destroy",  # Alias for app:destroy
        "backup:delete",
        "services:destroy",
    }

    return command in destructive_commands


def confirm_destructive_action(cli_args: list[str], printer: RichPrinter) -> bool:
    """Prompt user to confirm a destructive action.

    Args:
        cli_args: Command-line arguments
        printer: Printer for output (for JSON mode detection)

    Returns:
        True if user confirmed, False if cancelled
    """
    if printer.json_output:
        # In JSON mode, auto-confirm (user should use -y flag)
        return True

    command = cli_args[0]
    args = cli_args[1:]

    # app:destroy or destroy command - requires type-to-confirm
    if command in {"app:destroy", "destroy"}:
        if not args:
            # No app name provided, let server handle error
            return True

        app_name = args[0]
        show_destructive_warning(
            "destroy",
            f"app '{app_name}'",
            "All files, data, and configuration will be permanently deleted.",
        )
        return type_to_confirm(f"Type '{app_name}' to confirm:", app_name)

    # backup:delete command
    if command == "backup:delete":
        if not args:
            return True

        backup_id = args[0]
        show_destructive_warning(
            "delete",
            f"backup '{backup_id}'",
            "This backup cannot be recovered once deleted.",
        )
        return confirm("Are you sure you want to delete this backup?")

    # services:destroy command
    if command == "services:destroy":
        if not args:
            return True

        addon_name = args[0]
        show_destructive_warning(
            "destroy",
            f"service '{addon_name}'",
            "All data in this service will be permanently deleted.",
        )
        return type_to_confirm(f"Type '{addon_name}' to confirm:", addon_name)

    # Unknown destructive command (shouldn't happen)
    return confirm("This action cannot be undone. Continue?")
