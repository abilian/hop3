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


def _extract_app_flag(args: list[str]) -> str | None:
    """Return the value of `--app NAME` / `-a NAME` / `--app=NAME`, if present.

    App-scoped commands receive the app as a flag (ADR 036 D5), never as a
    positional, so the confirmation target must come from here — reading
    ``args[0]`` would grab the literal ``"--app"``.
    """
    for i, tok in enumerate(args):
        if tok in {"--app", "-a"} and i + 1 < len(args):
            return args[i + 1]
        if tok.startswith("--app="):
            return tok[len("--app=") :]
    return None


def _first_positional(args: list[str]) -> str | None:
    """First non-flag token (skipping `--app`/`-a` and the value it consumes)."""
    skip_next = False
    for tok in args:
        if skip_next:
            skip_next = False
            continue
        if tok in {"--app", "-a"}:
            skip_next = True
            continue
        if tok.startswith("-"):
            continue
        return tok
    return None


def _resolve_target_name(command: tuple[str, ...], args: list[str]) -> str | None:
    """The resource name the user must type (or pass to `--confirm`).

    App-scoped destroy takes the app from `--app NAME` (never positional);
    every other destructive command names its resource positionally (addon
    type, backup id, username, context). Returns None when absent.
    """
    if command in {("app", "destroy"), ("destroy",)}:
        return _extract_app_flag(args) or _first_positional(args)
    return _first_positional(args)


def confirm_destructive_action(  # noqa: PLR0911 — sequential decision tree, each return is a distinct escape hatch (json mode, no-match, missing-args, --confirm, --no-input, …) with its own side effects; flattening into a result var would obscure the safety story.
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

    # Resolve the resource the user must confirm. App-scoped commands pass the
    # app as `--app NAME` (ADR 036 D5, never positional); reading args[0] would
    # grab the literal "--app". Missing target → let the server error.
    target_name = _resolve_target_name(command, args)
    if target_name is None:
        return True

    # ADR 036 G6: --confirm=<name> matches → accept silently. Unlike --force it
    # is not a global safety bypass: the value must match the resource name.
    if flags and flags.confirm_value is not None:
        if flags.confirm_value != target_name:
            print(
                f"Error: --confirm value '{flags.confirm_value}' does not match "
                f"target '{target_name}'.",
                file=sys.stderr,
            )
            return False
        return True

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

    # ADR 036 D14: context-mismatch warning. If the user is about to act
    # on a resource in a non-default context, surface that explicitly.
    _maybe_show_context_warning(config)

    # app destroy (or destroy alias) - requires type-to-confirm
    if command in {("app", "destroy"), ("destroy",)}:
        return _confirm_app_destroy(target_name)

    # backup destroy command
    if command == ("backup", "destroy"):
        return _confirm_backup_delete(target_name)

    # addon destroy command
    if command == ("addon", "destroy"):
        return _confirm_service_destroy(target_name)

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


def _confirm_app_destroy(app_name: str) -> bool:
    """Confirm app destroy command."""
    show_destructive_warning(
        "destroy",
        f"app '{app_name}'",
        "All files, data, and configuration will be permanently deleted.",
    )
    return type_to_confirm(f"Type '{app_name}' to confirm:", app_name)


def _confirm_backup_delete(backup_id: str) -> bool:
    """Confirm backup destroy command."""
    show_destructive_warning(
        "delete",
        f"backup '{backup_id}'",
        "This backup cannot be recovered once deleted.",
    )
    return confirm("Are you sure you want to delete this backup?")


def _confirm_service_destroy(addon_name: str) -> bool:
    """Confirm services destroy command."""
    show_destructive_warning(
        "destroy",
        f"service '{addon_name}'",
        "All data in this service will be permanently deleted.",
    )
    return type_to_confirm(f"Type '{addon_name}' to confirm:", addon_name)
