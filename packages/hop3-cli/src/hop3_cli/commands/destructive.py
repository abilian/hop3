# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Destructive command handling and confirmation prompts."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from hop3_cli.ui.prompts import confirm, show_destructive_warning, type_to_confirm

if TYPE_CHECKING:
    from hop3_cli.commands.flags import CliFlags
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
    # Per-type addon operations that overwrite or wipe data. These reach the
    # generic confirmation prompt (no typed-name needed); --confirm=<name> /
    # --yes apply as usual. Note: `import` reads its dump from stdin, so it
    # can't prompt interactively — pass --confirm/--yes with it.
    ("addon", "postgres", "restore"),
    ("addon", "mysql", "restore"),
    ("addon", "redis", "restore"),
    ("addon", "s3", "restore"),
    ("addon", "postgres", "import"),
    ("addon", "mysql", "import"),
    ("addon", "redis", "import"),
    ("addon", "s3", "import"),
    ("addon", "redis", "flush"),
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


def confirm_destructive_action(  # noqa: PLR0911 — sequential decision tree, each return is a distinct escape hatch (json mode, no-match, missing-args, --confirm, --no-input, protected context, …) with its own side effects; flattening into a result var would obscure the safety story.
    cli_args: list[str],
    printer: RichPrinter,
    config: Config | None = None,
    *,
    flags: CliFlags | None = None,
) -> bool:
    """Prompt user to confirm a destructive action (ADR 036 D14, G6, G5).

    Confirmation has three escapes for non-interactive use, plus an
    interactive path:

    - ``--confirm <name>`` (G6): the scriptable form of typed-name
      confirmation. If the value matches the resource being destroyed,
      we accept without prompting and without disabling other safety checks.
    - ``--yes`` / ``-y`` / ``--force`` (D14): skip the prompt entirely.
      Coarser than ``--confirm`` — bypasses *all* checks including the
      typed-name guard, so use it only when intent is unambiguous.
    - ``--no-input`` (G5): refuse to prompt. If input would be required,
      fail with a one-line "use --confirm or --yes" instruction. For
      automation/CI where stdin isn't a terminal.
    - Interactive: standard typed-name or [y/N] prompt.

    Non-tty stdin without ``--yes``/``--confirm``/``--force`` refuses to
    proceed with the same instruction: never silently assume yes.

    Returns True if the user confirmed (or skipped), False if cancelled.
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

    target_name = args[0]

    # ADR 036 G6: --confirm=<name> matches → accept silently. This still
    # runs the protected-context check (which has its own confirmation),
    # so --confirm is *not* a global safety bypass like --force.
    if flags and flags.confirm_value is not None:
        if flags.confirm_value != target_name:
            print(
                f"Error: --confirm value '{flags.confirm_value}' does not match "
                f"target '{target_name}'.",
                file=sys.stderr,
            )
            return False
        # Still check protected context (has its own confirmation prompt).
        is_protected, context_name = _confirm_protected_context(config)
        return not (is_protected and context_name is None)

    # ADR 036 G5: --no-input refuses to prompt with an actionable message.
    # The implicit non-tty case is left to the prompt helpers, which catch
    # EOFError and abort with a "Aborted." message — safe by default, but
    # less informative. Users in CI/cron should explicitly pass --no-input
    # (or --yes / --confirm) to get the better instructions.
    if flags is not None and flags.no_input:
        print(
            f"Error: '{' '.join(command)} {target_name}' would prompt for confirmation, "
            f"but --no-input was passed.\n"
            f"  Use --confirm={target_name}  to acknowledge non-interactively (preserves other safety checks).\n"
            f"  Or --yes / --force          to skip the prompt entirely (less safe).",
            file=sys.stderr,
        )
        return False

    # Check if this is a protected context
    is_protected, context_name = _confirm_protected_context(config)
    if is_protected and context_name is None:
        # User cancelled protected context confirmation
        return False

    # ADR 036 D14: context-mismatch warning. If the user is about to act
    # on a resource in a non-default context, surface that explicitly.
    _maybe_show_context_warning(config)

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


def _maybe_show_context_warning(config: Config | None) -> None:
    """Emit a context-mismatch warning before destructive ops (ADR 036 D14).

    "Mismatch" here is shallow: we just print the active context so the
    user can spot at a glance if they're about to destroy in production.
    A deeper version would compare against an explicit "non-destructive"
    context — left for later if real usage shows the noise level matters.
    """
    if config is None:
        return
    name = config.get_current_context_name()
    if name:
        print(
            f"\n  ⚠  Acting in context '{name}'. Verify this is correct.\n",
            file=sys.stderr,
        )


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
