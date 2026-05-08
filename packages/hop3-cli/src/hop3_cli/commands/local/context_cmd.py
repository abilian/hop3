# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Context command - manage multiple server contexts."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_cli.commands.local.help_text import print_context_help
from hop3_cli.config import LOCAL_CONTEXT_FILE

# Context names flow into TOML keys and config-file paths. The shape
# below is the same lowercase-alpha-with-hyphens form server-side
# identifiers use, plus underscores and a digit/letter start. Keeps
# whitespace, quotes, dots, slashes and shell metacharacters out of
# the config file. Length capped at 64 (TOML keys aren't bounded but
# we don't want operators inventing 1KB context labels).
_CONTEXT_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _validate_context_name(name: str) -> bool:
    """Return True if ``name`` is a safe context identifier."""
    return bool(_CONTEXT_NAME_RE.fullmatch(name))


if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_context(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Handle the context command for managing server contexts.

    Usage:
        hop3 context                       Show current context state + subcommand list
        hop3 context list                  List all configured contexts
        hop3 context show [<name>]         Show details of a context
        hop3 context use [--app <a>] <n>   Switch active context (optionally set default app)
        hop3 context add <name> --server <url> [options]
        hop3 context remove <name>
        hop3 context rename <old> <new>

    Per ADR 036 D8: bare `hop3 context` prints the current active state AND a
    short hint to help new users discover subcommands without having to pass
    `--help`.
    """
    if args and args[0] in {"--help", "-h"}:
        print_context_help()
        return

    if not args:
        _context_bare(config, printer)
        return

    subcommand = args[0]
    sub_args = args[1:]

    if subcommand == "list":
        context_list(config, printer)
    elif subcommand == "show":
        context_show(sub_args, config, printer)
    elif subcommand == "use":
        context_use(sub_args, config, printer)
    elif subcommand == "add":
        context_add(sub_args, config, printer)
    elif subcommand == "remove":
        context_remove(sub_args, config, printer)
    elif subcommand == "rename":
        context_rename(sub_args, config, printer)
    else:
        print(f"Unknown context subcommand: {subcommand}", file=sys.stderr)
        print_context_help()
        sys.exit(1)


def _context_bare(config: Config, printer: RichPrinter) -> None:
    """Bare `hop3 context` — show current state + a short discoverability hint.

    Per ADR 036 D8: answers the implicit question "what would happen if I ran
    an app-scoped command right now?".
    """
    current = config.get_current_context_name()
    context = config.get_current_context()

    if current and context:
        source = _get_context_source(config, current)
        print(f"Current context: {current}  (via {source})")
        print(f"  Server:      {context.api_url}")
        if context.protected:
            print("  Protected:   yes")
        if context.default_app:
            print(f"  Default app: {context.default_app}")
        else:
            print("  Default app: (none — set with `hop3 use <app>`)")
    else:
        print("No active context.")
        if config.has_contexts():
            print("  Use `hop3 context use <name>` to select one.")
        else:
            print("  Use `hop3 context add <name> --server <url>` to create one.")

    print()
    print("Subcommands: list, show, use, add, remove, rename")
    print("Run `hop3 context --help` for details.")


def context_list(config: Config, printer: RichPrinter) -> None:
    """List all configured contexts."""
    contexts = config.get_contexts()
    current = config.get_current_context_name()

    if not contexts:
        print("No contexts configured.")
        print("\nTo add a context:")
        print("  hop3 context add staging --server ssh://root@staging.example.com")
        return

    print("Configured contexts:\n")
    for name, ctx in sorted(contexts.items()):
        marker = "*" if name == current else " "
        protected = " [protected]" if ctx.protected else ""
        print(f"  {marker} {name}{protected}")
        print(f"      Server: {ctx.api_url}")
        if ctx.api_token:
            token_display = (
                ctx.api_token[:20] + "..." if len(ctx.api_token) > 20 else ctx.api_token
            )
            print(f"      Token: {token_display}")

    print(f"\nCurrent context: {current or '(none)'}")


def context_show(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Show details of a context (by name, or the currently active one)."""
    target: str | None
    if args and not args[0].startswith("--"):
        target = args[0]
    else:
        target = config.get_current_context_name()

    if not target:
        print("No current context set.")
        if config.has_contexts():
            print("\nUse 'hop3 context use <name>' to select a context.")
        else:
            print("\nUse 'hop3 context add <name> --server <url>' to add a context.")
        return

    contexts = config.get_contexts()
    context = contexts.get(target)
    if not context:
        print(f"Context '{target}' not found.", file=sys.stderr)
        if contexts:
            print(f"\nAvailable contexts: {', '.join(sorted(contexts.keys()))}")
        sys.exit(1)

    active = config.get_current_context_name()
    is_active = target == active
    print(f"Context: {target}{' (active)' if is_active else ''}")
    if is_active:
        print(f"  Source:      {_get_context_source(config, target)}")
    print(f"  Server:      {context.api_url}")
    if context.protected:
        print("  Protected:   yes (requires confirmation for destructive operations)")
    if context.default_app:
        print(f"  Default app: {context.default_app}")
    if context.api_token:
        token_display = (
            context.api_token[:20] + "..."
            if len(context.api_token) > 20
            else context.api_token
        )
        print(f"  Token:       {token_display}")


def _get_context_source(config: Config, context_name: str) -> str:
    """Determine where the current context setting came from."""
    # Check in priority order
    if config.has_context_override():
        return "--context flag"

    env_context = os.environ.get("HOP3_CONTEXT")
    if env_context:
        return "HOP3_CONTEXT environment variable"

    local_file = Path.cwd() / LOCAL_CONTEXT_FILE
    if local_file.exists():
        try:
            content = local_file.read_text().strip()
            if content == context_name:
                return f"local file ({local_file})"
        except OSError:
            pass

    return "global config"


def _parse_context_use_args(
    args: list[str],
) -> tuple[str | None, bool, bool, str | None]:
    """Parse context use arguments.

    Returns:
        Tuple of (context_name, use_local, use_global, app).
        `app` is the value of `--app <name>` if given (ADR 036 D7/D8).
    """
    use_local = "--local" in args
    use_global = "--global" in args

    app: str | None = None
    name: str | None = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {"--app", "-a"} and i + 1 < len(args):
            app = args[i + 1]
            i += 2
            continue
        if not arg.startswith("--") and arg != "-a" and name is None:
            name = arg
        i += 1

    return name, use_local, use_global, app


def _context_use_global(name: str, config: Config, context) -> None:
    """Handle --global flag for context use."""
    config.set_global_context(name)
    print(f"Set global default context to '{name}'")
    print("  Warning: This affects ALL terminals and shells.")
    if context and context.protected:
        print("  Warning: This is a protected context.")


def _context_use_local(name: str, config: Config, context) -> None:
    """Handle --local flag for context use."""
    local_path = config.write_local_context(name)
    print(f"Wrote context '{name}' to {local_path}")
    print("  This context will be used when running hop3 from this directory.")
    if context and context.protected:
        print("  Warning: This is a protected context.")
    print("\n  Tip: Add .hop3-context to .gitignore if you don't want to commit it.")


def _context_use_default(name: str, context) -> None:
    """Handle default behavior for context use (print export command)."""
    print(f"To use context '{name}' in this shell, run:\n")
    print(f"  export HOP3_CONTEXT={name}\n")
    if context:
        print(f"Server: {context.api_url}")
        if context.protected:
            print("Warning: This is a protected context.")
    print("\nOther options:")
    print(f"  hop3 context use {name} --local   # Save to .hop3-context file")
    print(
        f"  hop3 context use {name} --global  # Set as global default (all terminals)"
    )


def context_use(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Switch to a different context (ADR 036 D7/D8).

    By default, prints instructions to set the environment variable (safest).
    Use --local to write to .hop3-context file in current directory.
    Use --global to persist to global config (affects all terminals).
    Use --app <name> to also set the context's default app in one shot.
    """
    if not args:
        _print_context_use_usage()
        sys.exit(1)

    name, use_local, use_global, app = _parse_context_use_args(args)

    if not name:
        _print_context_use_usage()
        sys.exit(1)

    # Validate context exists
    if not config.use_context(name):
        print(f"Context '{name}' not found.", file=sys.stderr)
        contexts = config.get_contexts()
        if contexts:
            print(f"\nAvailable contexts: {', '.join(sorted(contexts.keys()))}")
        sys.exit(1)

    # Get context details for display
    context = config.get_contexts().get(name)

    # Apply --app (if any): sets the context's default_app. This works
    # independently of --local/--global/(default) scope because it's always
    # persisted to the named context's entry.
    if app is not None:
        config.set_default_app(app, context_name=name)
        print(f"Set default app for context '{name}' to '{app}'.")

    if use_global:
        _context_use_global(name, config, context)
    elif use_local:
        _context_use_local(name, config, context)
    else:
        _context_use_default(name, context)


def _print_context_use_usage() -> None:
    print(
        "Usage: hop3 context use [--local | --global] [--app <name>] <name>",
        file=sys.stderr,
    )
    print("\nOptions:")
    print("  (default)       Print export command for this shell only")
    print("  --local         Write to .hop3-context in current directory")
    print("  --global        Set as global default (affects all terminals)")
    print("  --app <name>    Also set this context's default app (ADR 036 D7/D8)")


def context_rename(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Rename a context: `hop3 context rename <old> <new>`."""
    if len(args) < 2:
        print("Usage: hop3 context rename <old-name> <new-name>", file=sys.stderr)
        sys.exit(1)

    old_name, new_name = args[0], args[1]
    contexts = config.get_contexts()

    if old_name not in contexts:
        print(f"Context '{old_name}' not found.", file=sys.stderr)
        sys.exit(1)
    if new_name in contexts:
        print(
            f"Context '{new_name}' already exists. Pick a different name or remove the existing one first.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not _validate_context_name(new_name):
        print(
            f"Invalid context name: {new_name!r} — must match "
            f"{_CONTEXT_NAME_RE.pattern!r} (letters/digits with optional "
            "hyphens or underscores, 1-64 chars).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Copy old context data under new name, then remove old.
    old_ctx = contexts[old_name]
    config.add_context(
        name=new_name,
        api_url=old_ctx.api_url,
        api_token=old_ctx.api_token,
        protected=old_ctx.protected,
        ssh_user=old_ctx.ssh_user,
        ssh_port=old_ctx.ssh_port,
    )
    # Preserve non-canonical fields not covered by add_context's args.
    config.data["contexts"][new_name]["ssh_key"] = old_ctx.ssh_key
    config.data["contexts"][new_name]["ssl_cert"] = old_ctx.ssl_cert
    config.data["contexts"][new_name]["verify_ssl"] = old_ctx.verify_ssl
    config.data["contexts"][new_name]["default_app"] = old_ctx.default_app

    # If the old context was the global current, retarget it.
    if config.data.get("current_context") == old_name:
        config.data["current_context"] = new_name

    config.remove_context(old_name)

    print(f"Renamed context '{old_name}' -> '{new_name}'.")


def _parse_context_add_args(
    args: list[str],
) -> tuple[str, str | None, str, bool, bool, str, int]:
    """Parse arguments for context add command.

    Returns:
        Tuple of (name, server, token, protected, set_default, ssh_user, ssh_port)
    """
    name = args[0]
    remaining = args[1:]

    server = None
    token = ""
    protected = False
    set_default = False
    ssh_user = "root"
    ssh_port = 22

    i = 0
    while i < len(remaining):
        arg = remaining[i]
        if arg == "--server" and i + 1 < len(remaining):
            server = remaining[i + 1]
            i += 2
        elif arg == "--token" and i + 1 < len(remaining):
            token = remaining[i + 1]
            i += 2
        elif arg == "--protected":
            protected = True
            i += 1
        elif arg == "--default":
            set_default = True
            i += 1
        elif arg == "--ssh-user" and i + 1 < len(remaining):
            ssh_user = remaining[i + 1]
            i += 2
        elif arg == "--ssh-port" and i + 1 < len(remaining):
            ssh_port = int(remaining[i + 1])
            i += 2
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            sys.exit(1)

    return name, server, token, protected, set_default, ssh_user, ssh_port


def context_add(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Add a new context."""
    if not args:
        print(
            "Usage: hop3 context add <name> --server <url> [options]", file=sys.stderr
        )
        print("\nOptions:")
        print("  --server <url>     Server URL (required)")
        print("  --token <token>    API authentication token")
        print("  --protected        Mark as protected (requires confirmation)")
        print("  --default          Set as the default context")
        print("  --ssh-user <user>  SSH username (default: root)")
        print("  --ssh-port <port>  SSH port (default: 22)")
        sys.exit(1)

    name, server, token, protected, set_default, ssh_user, ssh_port = (
        _parse_context_add_args(args)
    )

    if not server:
        print("Error: --server is required", file=sys.stderr)
        sys.exit(1)

    if not _validate_context_name(name):
        print(
            f"Invalid context name: {name!r} — must match "
            f"{_CONTEXT_NAME_RE.pattern!r} (letters/digits with optional "
            "hyphens or underscores, 1-64 chars).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check if context already exists
    contexts = config.get_contexts()
    if name in contexts:
        print(
            f"Context '{name}' already exists. Use 'hop3 context remove {name}' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Add the context
    config.add_context(
        name=name,
        api_url=server,
        api_token=token,
        protected=protected,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
    )

    print(f"Added context '{name}'")
    print(f"  Server: {server}")
    if protected:
        print("  Protected: yes")

    # Set as default if requested or if it's the first context
    is_first_context = len(config.get_contexts()) == 1
    if set_default or is_first_context:
        config.set_global_context(name)
        if set_default:
            print(f"\nContext '{name}' is now the default.")
        else:
            print(f"\nContext '{name}' is now current (first context).")


def context_remove(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Remove a context."""
    if not args:
        print("Usage: hop3 context remove <name>", file=sys.stderr)
        sys.exit(1)

    name = args[0]

    # Check if it's the current context
    current = config.get_current_context_name()
    if name == current:
        print(f"Warning: '{name}' is the current context.")

    try:
        config.remove_context(name)
    except KeyError:
        print(f"Context '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Removed context '{name}'")

    # If we removed the current context, show the new current
    new_current = config.get_current_context_name()
    if new_current:
        print(f"Current context is now '{new_current}'")
    else:
        print("No current context set.")
