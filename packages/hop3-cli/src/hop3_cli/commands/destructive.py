# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Destructive command handling and confirmation prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_cli.ui.prompts import confirm, show_destructive_warning, type_to_confirm

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


"""Space-separated command-name tuples, per ADR 036 D1."""
# Destructive commands that require confirmation. Each entry is a tuple of tokens.
DESTRUCTIVE_COMMANDS: set[tuple[str, ...]] = {
    ("app", "destroy"),
    ("destroy",),  # Alias for app destroy
    ("backup", "destroy"),  # ADR 036 D4: destroy (was `backup delete`)
    ("addon", "destroy"),
    ("user", "remove"),
    ("context", "remove"),
}


def _match_destructive_prefix(cli_args: list[str]) -> tuple[str, ...] | None:
    """Return the destructive-command tuple that is a prefix of cli_args, if any."""
    for n in range(min(len(cli_args), 3), 0, -1):
        key = tuple(cli_args[:n])
        if key in DESTRUCTIVE_COMMANDS:
            return key
    return None


def is_destructive_command(cli_args: list[str]) -> bool:
    """Check if the command is destructive (requires confirmation).

    Args:
        cli_args: Command-line arguments (may be multiple tokens for the command name)

    Returns:
        True if command is destructive, False otherwise
    """
    if not cli_args:
        return False
    return _match_destructive_prefix(cli_args) is not None


def _confirm_protected_context(config: Config | None) -> tuple[bool, str | None]:
    """Check if context is protected and confirm if needed.

    Returns:
        Tuple of (is_protected, context_name).
        Returns (False, None) if user cancelled the confirmation.
    """
    if not config:
        return False, None

    is_protected = config.is_protected_context()
    context_name = config.get_current_context_name()

    if not is_protected:
        return False, context_name

    # Show extra warning for protected contexts
    print(f"\n  WARNING: You are operating on protected context '{context_name}'")
    print("  This context is marked as protected to prevent accidental changes.\n")

    if not confirm("Are you sure you want to continue with this destructive action?"):
        # Signal cancellation by returning special value
        return True, None  # is_protected=True but context_name=None means cancelled

    return True, context_name


def confirm_destructive_action(
    cli_args: list[str], printer: RichPrinter, config: Config | None = None
) -> bool:
    """Prompt user to confirm a destructive action.

    For protected contexts, extra confirmation is required.

    Args:
        cli_args: Command-line arguments
        printer: Printer for output (for JSON mode detection)
        config: Configuration for checking protected context (optional)

    Returns:
        True if user confirmed, False if cancelled
    """
    if printer.json_output:
        # In JSON mode, auto-confirm (user should use -y flag)
        return True

    # Match the destructive-command prefix (may be 1, 2, or 3 tokens).
    command = _match_destructive_prefix(cli_args)
    if command is None:
        return True
    args = cli_args[len(command) :]

    # Check if required arguments are present BEFORE any confirmation prompts.
    # If missing, let the server handle the error message.
    if not _has_required_args(command, args):
        return True

    # Check if this is a protected context
    is_protected, context_name = _confirm_protected_context(config)
    if is_protected and context_name is None:
        # User cancelled protected context confirmation
        return False

    # app destroy (or destroy alias) - requires type-to-confirm
    if command in {("app", "destroy"), ("destroy",)}:
        return _confirm_app_destroy(args, is_protected, context_name)

    # backup destroy command
    if command == ("backup", "destroy"):
        return _confirm_backup_delete(args)

    # addon destroy command
    if command == ("addon", "destroy"):
        return _confirm_service_destroy(args, is_protected, context_name)

    # Unknown destructive command (shouldn't happen)
    return confirm("This action cannot be undone. Continue?")


def _has_required_args(command: tuple[str, ...], args: list[str]) -> bool:
    """Check if a destructive command has its required arguments.

    Args:
        command: The command name tuple
        args: The arguments (excluding the command itself)

    Returns:
        True if required args are present, False otherwise
    """
    # All destructive commands currently require at least one positional argument
    # (the name of the resource being destroyed).
    return len(args) >= 1


def _confirm_app_destroy(
    args: list[str], is_protected: bool, context_name: str | None
) -> bool:
    """Confirm app destroy command."""
    app_name = args[0]
    show_destructive_warning(
        "destroy",
        f"app '{app_name}'",
        "All files, data, and configuration will be permanently deleted.",
    )

    # For protected contexts, require typing context name AND app name
    if is_protected and context_name:
        confirm_text = f"{context_name}/{app_name}"
        return type_to_confirm(
            f"Type '{confirm_text}' to confirm (context/app):", confirm_text
        )
    return type_to_confirm(f"Type '{app_name}' to confirm:", app_name)


def _confirm_backup_delete(args: list[str]) -> bool:
    """Confirm backup destroy command."""
    backup_id = args[0]
    show_destructive_warning(
        "delete",
        f"backup '{backup_id}'",
        "This backup cannot be recovered once deleted.",
    )
    return confirm("Are you sure you want to delete this backup?")


def _confirm_service_destroy(
    args: list[str], is_protected: bool, context_name: str | None
) -> bool:
    """Confirm services destroy command."""
    addon_name = args[0]
    show_destructive_warning(
        "destroy",
        f"service '{addon_name}'",
        "All data in this service will be permanently deleted.",
    )

    # For protected contexts, require typing context name AND service name
    if is_protected and context_name:
        confirm_text = f"{context_name}/{addon_name}"
        return type_to_confirm(
            f"Type '{confirm_text}' to confirm (context/service):", confirm_text
        )
    return type_to_confirm(f"Type '{addon_name}' to confirm:", addon_name)
