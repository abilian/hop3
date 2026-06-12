# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`hop3 server` verbs (ADR 042 §CLI verbs).

These verbs manage **server bindings** — the post-ADR-042 name for what
the CLI used to call "contexts" globally. A server binding is a record
of how to reach one Hop3 host: URL, auth token, SSH settings, optional
default app fallback.

Verbs:
- ``hop3 server list`` — list configured servers
- ``hop3 server add <name> --url <u> [...]`` — register a new server
- ``hop3 server remove <name>`` — drop a server
- ``hop3 server show <name>`` — display a server's details
- ``hop3 server use <name>`` — set the global single-server default
- ``hop3 server use --default-app <app>`` — set the current server's
  app-resolution fallback (ADR 042 app source #8)
- ``hop3 server login <name>`` — re-auth (token rotation, etc.)

The first call to any ``hop3 server`` verb runs the lazy migration
from legacy ``config.toml [contexts.*]`` into the new
``servers.toml [servers.*]`` location. The legacy file is preserved
(renamed to ``config.toml.pre-042.bak``) so operators can roll back.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_cli.core.cli_state import (
    get_current_server,
    set_current_server,
)
from hop3_cli.core.context_names import (
    InvalidContextNameError,
    validate_context_name,
)
from hop3_cli.core.server_registry import (
    LEGACY_BACKUP_FILENAME,
    LEGACY_CONFIG_FILENAME,
    ServerRecord,
    ServerRegistry,
    load_registry,
    migrate_legacy_records,
    remove,
    save_registry,
    upsert,
)

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_server(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Dispatch `hop3 server <subcommand>` verbs."""
    if args and args[0] in {"--help", "-h"}:
        _print_server_help()
        return

    if not args:
        _server_bare(config)
        return

    subcommand = args[0]
    sub_args = args[1:]

    handlers = {
        "list": server_list,
        "add": server_add,
        "remove": server_remove,
        "show": server_show,
        "use": server_use,
        "login": server_login,
    }
    handler = handlers.get(subcommand)
    if handler is None:
        print(
            f"Unknown server subcommand: {subcommand!r}. "
            f"Try one of: {', '.join(handlers)}.",
            file=sys.stderr,
        )
        sys.exit(1)
    registry = _load_with_lazy_migration(config)
    handler(sub_args, config, printer, registry)


def _print_server_help() -> None:
    from .help_text import SERVER_HELP  # noqa: PLC0415

    print(SERVER_HELP)


def _server_bare(config: Config) -> None:
    """Bare ``hop3 server`` — show registered servers + a subcommand hint."""
    registry = _load_with_lazy_migration(config)
    if not registry.records:
        print("No servers registered yet.")
        print("\nAdd one with:")
        print("  hop3 server add <name> --url <url>")
        return

    print(f"Servers (from {registry.path}):")
    for name in registry.names():
        rec = registry.records[name]
        print(f"  {name}: {rec.url}")
    print()
    print("Subcommands: list, add, remove, show, use, login")
    print("Run `hop3 server --help` for details.")


# ---- lazy migration ----------------------------------------------------


def _load_with_lazy_migration(config: Config) -> ServerRegistry:
    """Load the registry, running the legacy migration on first call.

    Conditions for running migration:
    - ``servers.toml`` doesn't exist yet (this is a fresh-of-Step-4 run).
    - ``config.toml`` has at least one ``[contexts.*]`` record.

    The migration writes ``servers.toml`` with the carried-over records
    and renames ``config.toml`` to ``config.toml.pre-042.bak`` so the
    legacy reader stops finding records. Operators get a one-time
    stderr summary of what was migrated.
    """
    # Default-path lookup; tests can override by patching default_servers_path.
    registry = load_registry()

    # Refuse to clobber an unparseable servers.toml.
    if registry.is_broken:
        print(
            f"Refusing to load: {registry.path} exists but failed to parse: "
            f"{registry.parse_error}. Fix or delete the file before "
            "running `hop3 server` verbs.",
            file=sys.stderr,
        )
        sys.exit(1)

    if registry.records:
        return registry  # Already migrated or freshly populated.

    legacy_contexts = config.data.get("contexts")
    if not isinstance(legacy_contexts, dict) or not legacy_contexts:
        return registry  # Nothing to migrate.

    migrated, names, notes = migrate_legacy_records(config.data, target=registry.path)
    save_registry(migrated)

    # Back up the legacy file so the next config.toml load doesn't see
    # contexts anymore. _backup_legacy_config preserves any pre-existing
    # .bak by appending a .N suffix.
    legacy_path = config.config_file or _legacy_config_path()
    if legacy_path and legacy_path.name == LEGACY_CONFIG_FILENAME:
        _backup_legacy_config(legacy_path)

    print(
        f"Migrated {len(names)} server record(s) from "
        f"{LEGACY_CONFIG_FILENAME} → {migrated.path}: {', '.join(names)}.",
        file=sys.stderr,
    )
    for note in notes:
        print(f"  note: {note}", file=sys.stderr)
    return migrated


def _backup_legacy_config(legacy_path: Path) -> None:
    """Move ``legacy_path`` aside, without clobbering an existing .bak.

    If ``config.toml.pre-042.bak`` already exists from a prior aborted
    migration run, we append a ``.N`` suffix so the older backup isn't
    silently lost. Prints the chosen target so operators see exactly
    where their old config went.
    """
    candidate = legacy_path.with_name(LEGACY_BACKUP_FILENAME)
    suffix_n = 0
    while candidate.exists():
        suffix_n += 1
        candidate = legacy_path.with_name(f"{LEGACY_BACKUP_FILENAME}.{suffix_n}")
    try:
        os.replace(legacy_path, candidate)
    except OSError as exc:
        print(
            f"warning: could not back up legacy {LEGACY_CONFIG_FILENAME} "
            f"to {candidate.name}: {exc}. The migration to servers.toml "
            "succeeded; the legacy file is still in place.",
            file=sys.stderr,
        )
        return
    print(
        f"Legacy file backed up to {candidate.name}.",
        file=sys.stderr,
    )


def _legacy_config_path() -> Path | None:
    """Best-effort guess at the legacy config.toml path."""
    try:
        from platformdirs import user_config_dir  # noqa: PLC0415
    except ImportError:
        return None
    return Path(user_config_dir("hop3-cli", "Abilian SAS")) / LEGACY_CONFIG_FILENAME


# ---- hop3 server list --------------------------------------------------


def server_list(
    args: list[str],
    config: Config,
    printer: RichPrinter,
    registry: ServerRegistry,
) -> None:
    """List all configured servers."""
    if args and args[0] in {"--help", "-h"}:
        print("Usage: hop3 server list")
        return

    if not registry.records:
        print("No servers registered.")
        print("\nAdd one with:")
        print("  hop3 server add <name> --url <url>")
        return

    current = _global_default_server_name(config)
    print(f"Servers (from {registry.path}):")
    print()
    for name in registry.names():
        rec = registry.records[name]
        marker = "*" if name == current else " "
        print(f"  {marker} {name}")
        print(f"      URL:         {rec.url}")
        if rec.protected:
            print("      Protected:   yes")
        if rec.default_app:
            print(f"      Default app: {rec.default_app}")
        if rec.token:
            print(f"      Token:       {_redact_token(rec.token)}")
    if current:
        print(f"\nGlobal default: {current}")


def _global_default_server_name(config: Config) -> str | None:
    """Return the global single-server default name, if set.

    Reads from ``~/.config/hop3-cli/state.toml`` (the ADR 042 location).
    Falls back to the legacy ``config.data['current_context']`` for one
    release so operators who haven't yet run ``hop3 server use`` after
    upgrading still see their old default. Step 7 retires the legacy
    fallback.
    """
    state = get_current_server()
    if state:
        return state
    legacy = config.data.get("current_context")
    return legacy if isinstance(legacy, str) and legacy else None


def _redact_token(token: str) -> str:
    """Mask a token for display.

    Returns ``'(set)'`` or ``'(not set)'``. We deliberately avoid showing
    any prefix/suffix bytes — JWTs have low-entropy headers (``eyJhbGci``
    is essentially fixed for HS256) and partial-disclosure patterns leak
    identification across screenshots and bug reports. ADR 042 specifies
    only 'masked token' without a length budget, so the safe default is
    the binary set/unset signal.
    """
    return "(set)" if token else "(not set)"


# ---- hop3 server add ---------------------------------------------------


def server_add(
    args: list[str],
    config: Config,
    printer: RichPrinter,
    registry: ServerRegistry,
) -> None:
    """Register a new server: ``hop3 server add <name> --url <u> [...]``."""
    if not args or args[0] in {"--help", "-h"}:
        print(
            "Usage: hop3 server add <name> --url <url> [--token <t>] "
            "[--ssh-user <u>] [--ssh-port <p>] [--protected]"
        )
        return

    name = args[0]
    try:
        validate_context_name(name)  # Same naming rules as project contexts.
    except InvalidContextNameError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    parsed, error = _parse_add_args(args[1:])
    if error is not None:
        print(error, file=sys.stderr)
        sys.exit(1)
    if not parsed["url"]:
        print("Error: --url is required.", file=sys.stderr)
        sys.exit(1)

    if name in registry.records:
        print(
            f"Server {name!r} already exists. Remove it first with "
            f"`hop3 server remove {name}`.",
            file=sys.stderr,
        )
        sys.exit(1)

    record = ServerRecord(
        name=name,
        url=parsed["url"],
        token=parsed.get("token", ""),
        ssh_user=parsed.get("ssh_user", "root"),
        ssh_port=parsed.get("ssh_port", 22),
        protected=parsed.get("protected", False),
    )
    save_registry(upsert(registry, record))
    print(f"Added server {name!r}: {record.url}")


# Pair-valued flags for `server add`: flag → (parsed-dict key, coercer).
_ADD_PAIR_FLAGS: dict[str, tuple[str, type]] = {
    "--url": ("url", str),
    "--token": ("token", str),
    "--ssh-user": ("ssh_user", str),
    "--ssh-port": ("ssh_port", int),
}
# Boolean (single-token) flags.
_ADD_BOOL_FLAGS: dict[str, str] = {
    "--protected": "protected",
}


def _parse_add_args(args: list[str]) -> tuple[dict, str | None]:
    """Parse ``server add`` flags. Returns ``(parsed_dict, error_or_None)``.

    Table-driven so the function stays below the lint complexity ceiling
    as flags grow. ``_ADD_PAIR_FLAGS`` lists ``--flag <value>`` pairs;
    ``_ADD_BOOL_FLAGS`` lists single-token boolean flags.
    """
    parsed: dict = {
        "url": "",
        "token": "",
        "ssh_user": "root",
        "ssh_port": 22,
        "protected": False,
    }
    i = 0
    while i < len(args):
        flag = args[i]
        if flag in _ADD_BOOL_FLAGS:
            parsed[_ADD_BOOL_FLAGS[flag]] = True
            i += 1
            continue
        if flag in _ADD_PAIR_FLAGS:
            key, coercer = _ADD_PAIR_FLAGS[flag]
            if i + 1 >= len(args):
                return parsed, f"Error: {flag} requires a value."
            try:
                parsed[key] = coercer(args[i + 1])
            except ValueError:
                return parsed, (
                    f"Error: {flag} must be a {coercer.__name__} (got {args[i + 1]!r})."
                )
            i += 2
            continue
        return parsed, f"Unknown option: {flag}"
    return parsed, None


# ---- hop3 server remove ------------------------------------------------


def server_remove(
    args: list[str],
    config: Config,
    printer: RichPrinter,
    registry: ServerRegistry,
) -> None:
    """Remove a server: ``hop3 server remove <name>``."""
    if not args or args[0] in {"--help", "-h"}:
        print("Usage: hop3 server remove <name>")
        return

    name = args[0]
    new_registry, removed = remove(registry, name)
    if not removed:
        print(f"Server {name!r} not found.", file=sys.stderr)
        if registry.records:
            print(f"\nAvailable: {', '.join(registry.names())}", file=sys.stderr)
        sys.exit(1)

    save_registry(new_registry)
    print(f"Removed server {name!r}.")
    if _global_default_server_name(config) == name:
        # Clear the now-dangling pointer so the next CLI call doesn't see
        # a broken state. Operators get a warning so they know to run
        # `hop3 server use <other>` to pick a new default.
        set_current_server(None)
        print(
            "warning: the removed server was the global default. "
            "Cleared the pointer; run `hop3 server use <other>` to pick a new one.",
            file=sys.stderr,
        )


# ---- hop3 server show --------------------------------------------------


def server_show(
    args: list[str],
    config: Config,
    printer: RichPrinter,
    registry: ServerRegistry,
) -> None:
    """Show a server's details: ``hop3 server show <name>``."""
    if not args or args[0] in {"--help", "-h"}:
        print("Usage: hop3 server show <name>")
        return

    name = args[0]
    rec = registry.get(name)
    if rec is None:
        print(f"Server {name!r} not found.", file=sys.stderr)
        if registry.records:
            print(f"\nAvailable: {', '.join(registry.names())}", file=sys.stderr)
        sys.exit(1)

    is_default = _global_default_server_name(config) == name
    print(f"Server: {name}{' (global default)' if is_default else ''}")
    print(f"  URL:         {rec.url}")
    print(f"  SSH user:    {rec.ssh_user}")
    print(f"  SSH port:    {rec.ssh_port}")
    print(f"  Protected:   {'yes' if rec.protected else 'no'}")
    print(f"  Default app: {rec.default_app or '(not set)'}")
    print(f"  Token:       {_redact_token(rec.token)}")


# ---- hop3 server use ---------------------------------------------------


def server_use(
    args: list[str],
    config: Config,
    printer: RichPrinter,
    registry: ServerRegistry,
) -> None:
    """Set the global single-server default OR set its default_app.

    Two distinct semantics:
    - ``hop3 server use <name>`` writes the global default in
      ``config.data['current_context']`` (matching legacy state-file
      shape until Step 7).
    - ``hop3 server use --default-app <app>`` writes ``default_app``
      onto the *current* server's record. This is the new app-
      resolution source #8 from ADR 042.
    """
    if not args or args[0] in {"--help", "-h"}:
        print(
            "Usage:\n"
            "  hop3 server use <name>                 Set as global default\n"
            "  hop3 server use --default-app <app>    "
            "Set current server's default_app"
        )
        return

    if args[0] == "--default-app":
        if len(args) < 2:
            print("Error: --default-app requires a value.", file=sys.stderr)
            sys.exit(1)
        _set_default_app_on_current(args[1], config, registry)
        return

    # Positional name → set as global default.
    name = args[0]
    if name not in registry.records:
        print(f"Server {name!r} not found.", file=sys.stderr)
        if registry.records:
            print(f"\nAvailable: {', '.join(registry.names())}", file=sys.stderr)
        sys.exit(1)

    # ADR 042: the global-default pointer lives in state.toml, separate
    # from config.toml (where unrelated operator preferences live).
    set_current_server(name)
    print(f"Set global default server to {name!r}.")


def _set_default_app_on_current(
    app: str, config: Config, registry: ServerRegistry
) -> None:
    """Write ``default_app`` onto the current server's record."""
    current = _global_default_server_name(config)
    if not current:
        print(
            "No global default server is set. Run `hop3 server use <name>` "
            "first, or pass `--server <name>` to commands.",
            file=sys.stderr,
        )
        sys.exit(1)
    rec = registry.get(current)
    if rec is None:
        print(
            f"Current default server {current!r} not in registry.",
            file=sys.stderr,
        )
        sys.exit(1)

    new_rec = ServerRecord(
        name=rec.name,
        url=rec.url,
        token=rec.token,
        ssh_user=rec.ssh_user,
        ssh_port=rec.ssh_port,
        ssh_key=rec.ssh_key,
        ssl_cert=rec.ssl_cert,
        verify_ssl=rec.verify_ssl,
        protected=rec.protected,
        default_app=app,
    )
    save_registry(upsert(registry, new_rec))
    print(f"Set default_app={app!r} on server {current!r}.")


# ---- hop3 server login -------------------------------------------------


def server_login(
    args: list[str],
    config: Config,
    printer: RichPrinter,
    registry: ServerRegistry,
) -> None:
    """Re-authenticate to a server: ``hop3 server login <name> [--token <t>]``.

    Minimal v1: token can be passed via ``--token``; richer auth flows
    (SSH bootstrap, magic-link) are deferred to the broader auth refactor.
    """
    if not args or args[0] in {"--help", "-h"}:
        print(
            "Usage: hop3 server login <name> --token <token>\n"
            "\n"
            "Rotates the auth token on an existing server record."
        )
        return

    name = args[0]
    rec = registry.get(name)
    if rec is None:
        print(f"Server {name!r} not found.", file=sys.stderr)
        sys.exit(1)

    token = ""
    i = 1
    while i < len(args):
        if args[i] == "--token" and i + 1 < len(args):
            token = args[i + 1]
            i += 2
        else:
            print(f"Unknown option: {args[i]}", file=sys.stderr)
            sys.exit(1)
    if not token:
        print("Error: --token is required.", file=sys.stderr)
        sys.exit(1)

    new_rec = ServerRecord(
        name=rec.name,
        url=rec.url,
        token=token,
        ssh_user=rec.ssh_user,
        ssh_port=rec.ssh_port,
        ssh_key=rec.ssh_key,
        ssl_cert=rec.ssl_cert,
        verify_ssl=rec.verify_ssl,
        protected=rec.protected,
        default_app=rec.default_app,
    )
    save_registry(upsert(registry, new_rec))
    print(f"Updated auth token for server {name!r}.")
