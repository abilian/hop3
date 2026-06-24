# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`hop3 context` — manage deploy environments in the project's hop3.toml.

ADR 042 (2nd revision): a *context* is a named deploy environment
(`[contexts.<name>]` in the committed `hop3.toml`) carrying non-secret config —
server address, app instance name, domains, env. The verbs here are the
imperative counterpart to hand-editing `hop3.toml`:

- ``list`` / ``show``      — read `[contexts.*]` from the nearest hop3.toml
- ``add`` / ``remove`` / ``rename`` — edit `[contexts.*]` (committed, shared)
- ``use``                 — pin a context for this checkout via
  ``.hop3-local.toml [local].context`` (gitignored, not committed)

Writes preserve the file's comments/order (tomlkit round-trip). No secrets ever
land in `hop3.toml`: the server is a literal address, never a token.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tomlkit

from hop3_cli.commands.local.help_text import print_context_help
from hop3_cli.core.hop3_toml import first_hop3_toml, read_hop3_toml
from hop3_cli.core.local_overlay import atomic_write_text, read_overlay, write_overlay

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter

# Context names flow into TOML keys; keep them shell-friendly (same shape as the
# server-side validator in project/schema.py).
_CONTEXT_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _validate_context_name(name: str) -> bool:
    return bool(_CONTEXT_NAME_RE.fullmatch(name))


def handle_context(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Dispatch `hop3 context <subcommand>` (ADR 042 r2)."""
    if args and args[0] in {"--help", "-h"}:
        print_context_help()
        return
    if not args:
        _context_bare()
        return

    subcommand, sub_args = args[0], args[1:]
    if subcommand == "list":
        context_list()
    elif subcommand == "show":
        context_show(sub_args)
    elif subcommand == "use":
        context_use(sub_args)
    elif subcommand == "add":
        context_add(sub_args, config)
    elif subcommand == "remove":
        context_remove(sub_args)
    elif subcommand == "rename":
        context_rename(sub_args)
    else:
        print(f"Unknown context subcommand: {subcommand}", file=sys.stderr)
        print_context_help()
        sys.exit(1)


# --------------------------------------------------------------------------
# Project hop3.toml location + read/write helpers
# --------------------------------------------------------------------------


def _locate_project_toml() -> Path | None:
    """Nearest hop3.toml at or above the CWD (capped at $HOME), or None."""
    path, _ = first_hop3_toml(Path.cwd(), Path.home())
    return path


def _require_project_toml() -> Path:
    path = _locate_project_toml()
    if path is None:
        print(
            "Error: no hop3.toml found in this directory or its parents. "
            "`hop3 context` manages deploy environments inside a project — "
            "create a hop3.toml (or run `hop3 init`) first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return path


def _read_contexts(path: Path) -> dict[str, dict[str, Any]]:
    """Return the `[contexts.*]` table from ``path`` (raw, read-only)."""
    raw = read_hop3_toml(path).get("contexts", {})
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)}


def _load_doc(path: Path) -> tomlkit.TOMLDocument:
    """Parse ``path`` with tomlkit (comments/order preserved for round-trip)."""
    try:
        return tomlkit.parse(path.read_text(encoding="utf-8"))
    except (OSError, tomlkit.exceptions.TOMLKitError) as exc:
        print(f"Error: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def _save_doc(path: Path, doc: tomlkit.TOMLDocument) -> None:
    atomic_write_text(path, tomlkit.dumps(doc))


def _context_domains(block: dict[str, Any]) -> list[str]:
    """Hostnames from a context block's `domains` (the `[domains].list` shape)."""
    dom = block.get("domains")
    if isinstance(dom, dict):
        return [h for h in dom.get("list", []) if isinstance(h, str)]
    return []


# --------------------------------------------------------------------------
# Read commands: bare / list / show
# --------------------------------------------------------------------------


def _current_selection() -> str | None:
    """The context pinned for this checkout (.hop3-local.toml [local].context)."""
    return read_overlay().current_context


def _context_bare() -> None:
    path = _locate_project_toml()
    if path is None:
        print("No hop3.toml here — `hop3 context` works inside a project.")
        print("\nSubcommands: list, show, use, add, remove, rename")
        return

    contexts = _read_contexts(path)
    current = _current_selection()
    if current and current in contexts:
        print(f"Current context: {current}  (via .hop3-local.toml)")
        print(f"  Server: {contexts[current].get('server', '(unset)')}")
    elif contexts:
        print(f"No context selected ({len(contexts)} declared in {path.name}).")
        print("  Pin one with `hop3 context use <name>`.")
    else:
        print(f"No contexts declared in {path}.")
        print("  Add one with `hop3 context add <name> --server <addr>`.")

    print("\nSubcommands: list, show, use, add, remove, rename")
    print("Run `hop3 context --help` for details.")


def context_list() -> None:
    """List `[contexts.*]` in the nearest hop3.toml + the current selection."""
    path = _require_project_toml()
    contexts = _read_contexts(path)
    current = _current_selection()

    if not contexts:
        print(f"No contexts declared in {path}.")
        print("\nTo add one:")
        print(
            "  hop3 context add prod --server ssh://root@prod.example.com --app myapp"
        )
        return

    print(f"Contexts in {path}:\n")
    for name, block in contexts.items():
        marker = "*" if name == current else " "
        print(f"  {marker} {name}")
        print(f"      server: {block.get('server', '(unset)')}")
        if block.get("app"):
            print(f"      app:    {block['app']}")
        if domains := _context_domains(block):
            print(f"      domains: {', '.join(domains)}")
    print(
        f"\nSelected (this checkout): {current or '(none — hop3 context use <name>)'}"
    )


def context_show(args: list[str]) -> None:
    """Show one context block (by name, or the current selection)."""
    path = _require_project_toml()
    contexts = _read_contexts(path)
    target = args[0] if args and not args[0].startswith("-") else _current_selection()

    if not target:
        print("No context selected. Pass a name or `hop3 context use <name>` first.")
        return
    block = contexts.get(target)
    if block is None:
        print(f"Context '{target}' not found in {path}.", file=sys.stderr)
        if contexts:
            print(f"\nDeclared: {', '.join(sorted(contexts))}")
        sys.exit(1)

    is_current = target == _current_selection()
    print(f"Context: {target}{' (selected)' if is_current else ''}")
    print(f"  server:  {block.get('server', '(unset)')}")
    if block.get("app"):
        print(f"  app:     {block['app']}")
    if domains := _context_domains(block):
        print(f"  domains: {', '.join(domains)}")
    if isinstance(block.get("env"), dict) and block["env"]:
        keys = ", ".join(sorted(block["env"]))
        print(f"  env:     {keys}")


# --------------------------------------------------------------------------
# Write commands: add / remove / rename (edit committed hop3.toml)
# --------------------------------------------------------------------------


def _parse_add_args(
    args: list[str],
) -> tuple[str, list[str], dict[str, str]]:
    """Parse `--server / --domain / --env` for `context add`.

    ``--app`` arrives via the global flag parser (config override), not here.
    Returns (server, domains, env). Exits on an unknown flag / missing value.
    """
    server = ""
    domains: list[str] = []
    env: dict[str, str] = {}
    i = 0
    while i < len(args):
        flag = args[i]
        if flag in {"--server", "-s"} and i + 1 < len(args):
            server = args[i + 1]
            i += 2
        elif flag in {"--domain", "--domains"} and i + 1 < len(args):
            domains.append(args[i + 1])
            i += 2
        elif flag == "--env" and i + 1 < len(args):
            key, sep, value = args[i + 1].partition("=")
            if not sep:
                print(
                    f"Error: --env expects KEY=VALUE, got {args[i + 1]!r}.",
                    file=sys.stderr,
                )
                sys.exit(1)
            env[key] = value
            i += 2
        else:
            print(f"Unknown or incomplete option: {flag}", file=sys.stderr)
            sys.exit(1)
    return server, domains, env


def context_add(args: list[str], config: Config) -> None:
    """Add `[contexts.<name>]` to the project's hop3.toml (committed, no secrets)."""
    if not args or args[0] in {"--help", "-h"}:
        print(
            "Usage: hop3 context add <name> --server <addr> [--app <app>] "
            "[--domain <d>]... [--env K=V]...\n"
            "\n"
            "Adds a deploy environment to the project's hop3.toml. The server is a\n"
            "literal address (no token — credentials live in the local store)."
        )
        return

    name = args[0]
    if not _validate_context_name(name):
        print(
            f"Invalid context name {name!r} — letters/digits then -/_ , max 64.",
            file=sys.stderr,
        )
        sys.exit(1)

    server, domains, env = _parse_add_args(args[1:])
    # --app is consumed by the global flag parser and reaches us via the override.
    app = config.get_app_override() or ""
    if not server:
        print("Error: --server <addr> is required.", file=sys.stderr)
        sys.exit(1)

    path = _require_project_toml()
    doc = _load_doc(path)
    contexts = doc.get("contexts")
    if contexts is None:
        contexts = tomlkit.table()
        doc["contexts"] = contexts
    if not isinstance(contexts, dict):
        print(f"Error: [contexts] in {path} is malformed.", file=sys.stderr)
        sys.exit(1)
    if name in contexts:
        print(
            f"Context {name!r} already exists in {path}. Remove it first with "
            f"`hop3 context remove {name}`.",
            file=sys.stderr,
        )
        sys.exit(1)

    block = tomlkit.table()
    block["server"] = server
    if app:
        block["app"] = app
    if domains:
        dom = tomlkit.table()
        dom["list"] = domains
        block["domains"] = dom
    if env:
        envt = tomlkit.table()
        for key, value in env.items():
            envt[key] = value
        block["env"] = envt
    contexts[name] = block

    _save_doc(path, doc)
    print(f"Added [contexts.{name}] to {path}.")
    print("  modified hop3.toml — commit it to share this environment.")


def context_remove(args: list[str]) -> None:
    """Delete `[contexts.<name>]` from the project's hop3.toml."""
    if not args:
        print("Usage: hop3 context remove <name>", file=sys.stderr)
        sys.exit(1)
    name = args[0]
    path = _require_project_toml()
    doc = _load_doc(path)
    contexts = doc.get("contexts")
    if not isinstance(contexts, dict) or name not in contexts:
        print(f"Context {name!r} not found in {path}.", file=sys.stderr)
        sys.exit(1)

    del contexts[name]
    _save_doc(path, doc)
    print(f"Removed [contexts.{name}] from {path}.")
    print("  modified hop3.toml — commit it.")
    if _current_selection() == name:
        print(
            f"  note: this checkout still selects '{name}' "
            "(.hop3-local.toml) — `hop3 context use <other>` to repoint."
        )


def context_rename(args: list[str]) -> None:
    """Rename `[contexts.<old>]` to `[contexts.<new>]` in the project's hop3.toml."""
    if len(args) < 2:
        print("Usage: hop3 context rename <old> <new>", file=sys.stderr)
        sys.exit(1)
    old_name, new_name = args[0], args[1]
    if not _validate_context_name(new_name):
        print(
            f"Invalid context name {new_name!r} — letters/digits then -/_ , max 64.",
            file=sys.stderr,
        )
        sys.exit(1)

    path = _require_project_toml()
    doc = _load_doc(path)
    contexts = doc.get("contexts")
    if not isinstance(contexts, dict) or old_name not in contexts:
        print(f"Context {old_name!r} not found in {path}.", file=sys.stderr)
        sys.exit(1)
    if new_name in contexts:
        print(f"Context {new_name!r} already exists in {path}.", file=sys.stderr)
        sys.exit(1)

    contexts[new_name] = contexts[old_name]
    del contexts[old_name]
    _save_doc(path, doc)
    print(f"Renamed [contexts.{old_name}] -> [contexts.{new_name}] in {path}.")
    print("  modified hop3.toml — commit it.")

    # If this checkout selected the old name, repoint the local pin.
    if _current_selection() == old_name:
        write_overlay({"local": {"context": new_name}})
        print(f"  repointed this checkout's selection to '{new_name}'.")


# --------------------------------------------------------------------------
# Selection: use (writes the gitignored per-checkout pin)
# --------------------------------------------------------------------------


def context_use(args: list[str]) -> None:
    """Pin a context for this checkout via .hop3-local.toml (not committed)."""
    if "--global" in args:
        print(
            "Error: --global was retired in ADR 042 r2 — a context is per-project "
            "now. `hop3 context use <name>` pins it for this checkout via "
            ".hop3-local.toml.",
            file=sys.stderr,
        )
        sys.exit(2)

    name = next((a for a in args if not a.startswith("-")), None)
    if not name:
        print("Usage: hop3 context use <name>", file=sys.stderr)
        sys.exit(1)

    path = _require_project_toml()
    contexts = _read_contexts(path)
    if name not in contexts:
        print(f"Context {name!r} not found in {path}.", file=sys.stderr)
        if contexts:
            print(f"\nDeclared: {', '.join(sorted(contexts))}")
        sys.exit(1)

    write_overlay({"local": {"context": name}})
    print(f"Selected context '{name}' for this checkout (.hop3-local.toml).")
    print("  local, not committed — each checkout chooses its own.")
