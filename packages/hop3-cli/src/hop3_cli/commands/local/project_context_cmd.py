# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Project-scoped `hop3 context` verbs (ADR 042 §CLI verbs).

This module implements the new meaning of `hop3 context` after ADR 042:
it manages project-level deploy targets declared in `hop3.toml` and
selected via `.hop3-local.toml`. The legacy meaning (global server
bindings) moves to `hop3 server` in Step 4.

Verbs:
- ``hop3 context list`` — list `[contexts.*]` blocks in the nearest
  hop3.toml plus which is currently selected
- ``hop3 context use <name>`` — write `.hop3-local.toml [current].context`
- ``hop3 context show [<name>]`` — print the resolved
  ``(server, app, domains, env)`` for a context
- ``hop3 context remove <name>`` — delete a `[contexts.<name>]` block
  from hop3.toml; warns if it was current
- ``hop3 context add <name> --server <s> [--app <a>] ...`` — add a stub
  context block to hop3.toml
- ``hop3 context init`` — interactively (or flag-driven) bootstrap a
  first context block + ``.hop3-local.toml`` for a project that has
  none yet

The CWD must contain ``hop3.toml`` (in CWD or an ancestor up to
``$HOME``) for any of these to make sense. The shared ``handle_context``
dispatcher in ``context_cmd.py`` checks this and routes legacy
(non-project) invocations to the global-server handler — transitional
until Step 4.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hop3_cli.core.context_names import (
    InvalidContextNameError,
    validate_context_name,
)
from hop3_cli.core.hop3_toml import first_hop3_toml, read_hop3_toml
from hop3_cli.core.local_overlay import (
    LOCAL_OVERLAY_FILENAME,
    atomic_write_toml,
    read_overlay,
    write_overlay,
)

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def find_project_hop3_toml(
    cwd: Path | None = None, home: Path | None = None
) -> Path | None:
    """Walk upward from ``cwd`` looking for ``hop3.toml``.

    Stops at ``home`` (inclusive). Returns the path of the nearest
    hop3.toml, or None if none is found.

    Note: this only checks *file existence*. The dispatcher in
    ``context_cmd.py`` additionally calls ``project_has_contexts`` to
    confirm the file actually declares ``[contexts.*]`` before routing
    to project-scoped behavior. A legacy-shape hop3.toml (no contexts
    block) falls through to the global-server dispatcher.
    """
    cwd = cwd or Path.cwd()
    home = home or Path.home()
    path, _ = first_hop3_toml(cwd, home)
    return path


def project_has_contexts(project_hop3: Path) -> bool:
    """True iff ``project_hop3`` declares at least one ``[contexts.*]`` block.

    Used by ``handle_context`` to decide whether to route to project-
    scoped behavior. Without this check a legacy-shape project (hop3.toml
    with no [contexts] section) would lose access to the global-server
    verbs from inside its directory.

    Returns False on parse failure so a broken hop3.toml routes to the
    legacy handler (which has nothing TOML-dependent to lose anyway).
    """
    return bool(_read_contexts(project_hop3))


def _read_contexts(path: Path) -> dict[str, dict[str, Any]]:
    """Read the [contexts] table from a hop3.toml, preserving order."""
    data = read_hop3_toml(path)
    contexts = data.get("contexts", {})
    if not isinstance(contexts, dict):
        return {}
    return {k: v for k, v in contexts.items() if isinstance(v, dict)}


def _current_context_name(cwd: Path, home: Path) -> str | None:
    """Return the context name selected in the nearest .hop3-local.toml.

    Used by `list` and `remove` to mark/warn about the active selection.
    Does NOT consult $HOP3_CONTEXT / --context flag — those are runtime
    overrides, not persistent state. The selected context is whatever the
    operator wrote to .hop3-local.toml.
    """
    return read_overlay(cwd=cwd, home=home).current_context


# =============================================================================
# hop3 context list
# =============================================================================


def project_context_list(
    args: list[str],
    project_hop3: Path,
    cwd: Path,
    home: Path,
    printer: RichPrinter,
    config: Config,
) -> None:
    """List `[contexts.*]` blocks in the nearest hop3.toml.

    Marks the currently-selected context with ``*``. Emits a warning for
    duplicate ``(server, app)`` resolutions (ADR 042 §Duplicate-target
    warning) — the warning surface is wired here but the full deploy-
    preview integration lands in Step 5.
    """
    if args and args[0] in {"--help", "-h"}:
        print("Usage: hop3 context list")
        print()
        print("Lists the [contexts.*] blocks declared in the nearest hop3.toml,")
        print("marks the currently-selected context with '*', and warns about")
        print("duplicate (server, app) targets.")
        return

    contexts = _read_contexts(project_hop3)
    if not contexts:
        print(f"No project contexts declared in {project_hop3}.")
        print("\nAdd one with:")
        print("  hop3 context add <name> --server <server> --app <app>")
        return

    current = _current_context_name(cwd, home)

    print(f"Project contexts (from {project_hop3}):")
    print()
    for name, block in contexts.items():
        marker = "*" if name == current else " "
        server = block.get("server", "(missing)")
        app = block.get("app", "(inherits [metadata].id)")
        print(f"  {marker} {name}")
        print(f"      Server: {server}")
        print(f"      App:    {app}")
        domains = block.get("domains")
        if isinstance(domains, list) and domains:
            print(f"      Domains: {', '.join(str(d) for d in domains)}")

    if current:
        print(f"\nCurrent context: {current}")
    else:
        print("\nCurrent context: (none — set with `hop3 context use <name>`)")

    _warn_duplicate_targets(contexts)


def _warn_duplicate_targets(contexts: dict[str, dict[str, Any]]) -> None:
    """Emit a stderr warning when two contexts resolve to the same target.

    Reused by the Step-5 deploy preview. Never a hard error per ADR 042 —
    legitimate aliasing exists (``prod`` and ``production`` pointing at
    the same deploy).
    """
    seen: dict[tuple[str, str], list[str]] = {}
    for name, block in contexts.items():
        server = block.get("server")
        app = block.get("app")
        if isinstance(server, str) and isinstance(app, str):
            seen.setdefault((server, app), []).append(name)

    for (server, app), names in seen.items():
        if len(names) > 1:
            joined = ", ".join(names)
            print(
                f"warning: contexts {{{joined}}} all resolve to "
                f"(server={server!r}, app={app!r})",
                file=sys.stderr,
            )


# =============================================================================
# hop3 context use
# =============================================================================


def project_context_use(
    args: list[str],
    project_hop3: Path,
    cwd: Path,
    home: Path,
    printer: RichPrinter,
    config: Config,
) -> None:
    """Set the currently-selected context (writes .hop3-local.toml).

    ADR 042 §CLI verbs: ``hop3 context use <name>`` writes
    ``[current].context = <name>`` to ``.hop3-local.toml``, creating the
    file and appending it to ``.gitignore`` when not already ignored.
    """
    if not args or args[0] in {"--help", "-h"}:
        print("Usage: hop3 context use <name>")
        print()
        print("Selects the project context for subsequent commands. The name")
        print("must match a [contexts.<name>] block in hop3.toml.")
        return

    name = args[0]
    contexts = _read_contexts(project_hop3)
    if name not in contexts:
        print(f"Context {name!r} not found in {project_hop3}.", file=sys.stderr)
        if contexts:
            available = ", ".join(contexts.keys())
            print(f"\nAvailable: {available}", file=sys.stderr)
        else:
            print(
                "\nNo contexts declared yet. Add one with `hop3 context add`.",
                file=sys.stderr,
            )
        sys.exit(1)

    path = write_overlay(
        {"current": {"context": name}},
        cwd=cwd,
        home=home,
        ensure_gitignore=True,
    )
    print(f"Wrote current context = {name!r} to {path}")


# =============================================================================
# hop3 context show
# =============================================================================


def project_context_show(
    args: list[str],
    project_hop3: Path,
    cwd: Path,
    home: Path,
    printer: RichPrinter,
    config: Config,
) -> None:
    """Print the (server, app, domains, env) for a context (resolved view).

    Without an arg, shows the currently-selected context. With an arg,
    shows the named context. The merge rules from ADR 042 §Merge
    semantics are applied so the displayed view matches what the
    resolver / deploy preview will see.
    """
    if args and args[0] in {"--help", "-h"}:
        print("Usage: hop3 context show [<name>]")
        return

    target = args[0] if args and not args[0].startswith("-") else None
    if target is None:
        target = _current_context_name(cwd, home)
        if target is None:
            print(
                "No current context selected. Run `hop3 context use <name>` "
                "or pass a name explicitly: `hop3 context show <name>`.",
                file=sys.stderr,
            )
            sys.exit(1)

    contexts = _read_contexts(project_hop3)
    block = contexts.get(target)
    if block is None:
        print(f"Context {target!r} not found in {project_hop3}.", file=sys.stderr)
        if contexts:
            print(f"\nAvailable: {', '.join(contexts.keys())}", file=sys.stderr)
        sys.exit(1)

    try:
        resolved = _resolve_view(project_hop3, target, block)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    current = _current_context_name(cwd, home)
    is_current = target == current

    print(f"Context: {target}{' (current)' if is_current else ''}")
    print(f"  Server:  {resolved['server']}")
    print(f"  App:     {resolved['app']}")
    domains = resolved["domains"]
    if domains:
        print(f"  Domains: {', '.join(domains)}")
    else:
        print("  Domains: (none)")
    env = resolved["env"]
    if env:
        print("  Env:")
        for k, v in env.items():
            print(f"    {k} = {v!r}")
    else:
        print("  Env:     (none)")


def _resolve_view(
    project_hop3: Path, name: str, block: dict[str, Any]
) -> dict[str, Any]:
    """Build the resolved (server, app, domains, env) view for ``name``.

    CLI-side equivalent of ``Hop3Config.resolve_context``. Applies the
    same merge rules from ADR 042 §Merge semantics:
    - app: context override else [metadata].id
    - domains: full replacement (context wins, including [] to blank)
    - env: merge with context-wins (both sides filtered of _policy /
      computed sub-tables)
    - server: required and non-empty (raises ValueError on miss),
      matching the server-side schema's invariant. Without this guard
      the CLI would print ``Server: `` (empty) and silently leak past
      what the deploy preview will accept.

    Raises:
        ValueError: when ``server`` is missing or empty on the block.
            The caller surfaces this as a focused error message.
    """
    data = read_hop3_toml(project_hop3)

    # ``server`` — required field. Schema-validated configs always have
    # it; ``validate=False`` paths or hand-edited hop3.toml might not.
    # Raise here so ``hop3 context show`` reports the actual problem
    # rather than silently displaying an empty Server field.
    raw_server = block.get("server")
    if not isinstance(raw_server, str) or not raw_server.strip():
        msg = (
            f"Context {name!r} is missing the required `server` field. "
            'Edit hop3.toml to add `server = "<name>"` under '
            f"[contexts.{name}]."
        )
        raise ValueError(msg)
    server = raw_server.strip()

    # ``app`` fallback chain.
    app = block.get("app")
    if not isinstance(app, str) or not app.strip():
        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            mid = metadata.get("id")
            app = mid if isinstance(mid, str) and mid.strip() else ""
    app = (app or "").strip()

    # ``domains`` full replacement.
    if "domains" in block:
        ctx_domains = block.get("domains") or []
        domains = [str(d) for d in ctx_domains if isinstance(d, str)]
    else:
        top_domains_block = data.get("domains", {})
        if isinstance(top_domains_block, dict):
            top_list = top_domains_block.get("list", []) or []
            domains = [str(d) for d in top_list if isinstance(d, str)]
        else:
            domains = []

    # ``env`` merge. Both sides go through the same filter as on the
    # server side (drop _policy keys + nested sub-tables).
    base_env = _filter_env(data.get("env", {}))
    overlay_env = _filter_env(block.get("env", {}))
    merged_env = {**base_env, **overlay_env}

    return {
        "server": server,
        "app": app,
        "domains": tuple(domains),
        "env": merged_env,
    }


def _filter_env(raw: Any) -> dict[str, Any]:
    """Same filter as Hop3Config.env / resolve_context's env merge.

    Strips keys beginning with `_` (e.g. ``_policy``) and nested
    sub-tables (e.g. ``computed``). Top-level-only sentinels do not
    survive the merge per ADR 042.
    """
    if not isinstance(raw, dict):
        return {}
    return {
        k: v
        for k, v in raw.items()
        if not k.startswith("_") and not isinstance(v, dict)
    }


# =============================================================================
# hop3 context remove
# =============================================================================


def project_context_remove(
    args: list[str],
    project_hop3: Path,
    cwd: Path,
    home: Path,
    printer: RichPrinter,
    config: Config,
) -> None:
    """Remove a `[contexts.<name>]` block from the project's hop3.toml.

    Warns if the removed context was the current selection. Does not
    delete ``.hop3-local.toml`` even when the current selection becomes
    stale; the next ``hop3 context use`` overwrites it.

    Note on TOML rewriting: this uses ``toml.dump`` which does NOT
    preserve comments or formatting from the original file. The operator
    keeps source comments by hand-editing hop3.toml directly when that
    matters.
    """
    if not args or args[0] in {"--help", "-h"}:
        print("Usage: hop3 context remove <name>")
        return

    name = args[0]
    data = read_hop3_toml(project_hop3)
    contexts = data.get("contexts", {})
    if not isinstance(contexts, dict) or name not in contexts:
        print(f"Context {name!r} not found in {project_hop3}.", file=sys.stderr)
        sys.exit(1)

    del contexts[name]
    if not contexts:
        # Drop the empty table to keep the file clean.
        data.pop("contexts", None)

    _write_hop3_toml(project_hop3, data)
    print(f"Removed [contexts.{name}] from {project_hop3}.")

    if _current_context_name(cwd, home) == name:
        print(
            "warning: the removed context was the current selection. "
            "Run `hop3 context use <other>` to pick a new one.",
            file=sys.stderr,
        )


def _write_hop3_toml(path: Path, data: dict[str, Any]) -> None:
    """Write ``data`` to ``path`` as TOML, atomically + durably.

    Uses the shared ``atomic_write_toml`` helper so hop3.toml writes
    have the same crash-safety profile as ``.hop3-local.toml`` writes.
    Note: TOML round-trip via ``toml.dump`` loses comments, key order
    in some cases, and blank-line layout. Operators who care about
    preserving those should edit hop3.toml by hand.
    """
    atomic_write_toml(path, data)


# =============================================================================
# hop3 context add
# =============================================================================


def project_context_add(
    args: list[str],
    project_hop3: Path,
    cwd: Path,
    home: Path,
    printer: RichPrinter,
    config: Config,
) -> None:
    """Add a stub `[contexts.<name>]` block to the project's hop3.toml.

    Flag-driven (no interactive prompting in this pass):

        hop3 context add <name> --server <server> [--app <app>] [--domain <d>]...

    ``--server`` is required (ADR 042 schema makes it mandatory).
    ``--app`` is optional (inherits from [metadata].id when absent).
    ``--domain`` may appear multiple times to build a list.
    """
    if not args or args[0] in {"--help", "-h"}:
        print(
            "Usage: hop3 context add <name> --server <server> [--app <a>] "
            "[--domain <d>]..."
        )
        return

    name = args[0]
    try:
        validate_context_name(name)
    except InvalidContextNameError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    server, app, domains, error = _parse_add_args(args[1:])
    if error is not None:
        print(error, file=sys.stderr)
        sys.exit(1)
    # See project_context_init: the global flag parser eats --server/--app,
    # so they normally arrive via config. Locally-parsed values win.
    server = server or config.get_server_override() or ""
    app = app or config.get_app_override() or ""
    if not server:
        print("Error: --server is required.", file=sys.stderr)
        sys.exit(1)

    data = read_hop3_toml(project_hop3)
    contexts = data.setdefault("contexts", {})
    if not isinstance(contexts, dict):
        print(
            f"Cannot add: [contexts] section in {project_hop3} is malformed.",
            file=sys.stderr,
        )
        sys.exit(1)
    if name in contexts:
        print(
            f"Context {name!r} already exists. Remove it first with "
            f"`hop3 context remove {name}`.",
            file=sys.stderr,
        )
        sys.exit(1)

    block: dict[str, Any] = {"server": server}
    if app:
        block["app"] = app
    if domains:
        block["domains"] = domains
    contexts[name] = block

    _write_hop3_toml(project_hop3, data)
    print(f"Added [contexts.{name}] to {project_hop3}.")


def _parse_add_args(
    args: list[str],
) -> tuple[str, str, list[str], str | None]:
    """Parse ``--server / --app / --domain`` flags.

    Returns ``(server, app, domains, error_message_or_None)``. The
    error message is non-None when an unknown flag or missing value is
    seen — caller prints and exits.
    """
    server = ""
    app = ""
    domains: list[str] = []
    i = 0
    while i < len(args):
        flag = args[i]
        if flag in {"--server", "-s"}:
            if i + 1 >= len(args):
                return "", "", [], f"Error: {flag} requires a value."
            server = args[i + 1]
            i += 2
        elif flag in {"--app", "-a"}:
            if i + 1 >= len(args):
                return "", "", [], f"Error: {flag} requires a value."
            app = args[i + 1]
            i += 2
        elif flag == "--domain":
            if i + 1 >= len(args):
                return "", "", [], "Error: --domain requires a value."
            domains.append(args[i + 1])
            i += 2
        else:
            return "", "", [], f"Unknown option: {flag}"
    return server, app, domains, None


# =============================================================================
# hop3 context init
# =============================================================================


def project_context_init(
    args: list[str],
    project_hop3: Path,
    cwd: Path,
    home: Path,
    printer: RichPrinter,
    config: Config,
) -> None:
    """Bootstrap a starter context for a project that has none yet.

    Flag-driven for predictability (no prompts in this pass):

        hop3 context init --server <server> [--app <app>] [--name <name>]

    Defaults: ``--name`` is ``dev``. ``--app`` inherits from
    ``[metadata].id`` when absent. ``--server`` is required.

    On success: writes the ``[contexts.<name>]`` block to hop3.toml AND
    writes ``.hop3-local.toml [current].context = <name>`` so the
    operator's first command is correctly targeted.
    """
    if args and args[0] in {"--help", "-h"}:
        print(
            "Usage: hop3 context init --server <server> [--app <app>] [--name <name>]"
        )
        print()
        print(
            "Creates the first project context. Writes [contexts.<name>] "
            "to hop3.toml AND .hop3-local.toml [current].context."
        )
        return

    server, app, name, error = _parse_init_args(args)
    if error is not None:
        print(error, file=sys.stderr)
        sys.exit(1)
    # `--server` / `--app` are consumed by the global flag parser (see
    # commands/flags.py) before this handler runs, so under normal CLI use
    # they arrive via config rather than args. A locally-parsed value
    # (direct/programmatic calls) still takes precedence.
    server = server or config.get_server_override() or ""
    app = app or config.get_app_override() or ""
    if not server:
        print(
            "Error: --server is required.\n"
            "Usage: hop3 context init --server <server> "
            "[--app <app>] [--name <name>]",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate the name BEFORE any file write — prevents the half-applied
    # state where hop3.toml gets a bad-named block and .hop3-local.toml is
    # never written (or vice versa).
    try:
        validate_context_name(name)
    except InvalidContextNameError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    data = read_hop3_toml(project_hop3)
    existing_contexts = data.get("contexts", {})
    if isinstance(existing_contexts, dict) and name in existing_contexts:
        print(
            f"Context {name!r} already exists in {project_hop3}.",
            file=sys.stderr,
        )
        print(
            f"Use `hop3 context add` to add a different one, or "
            f"`hop3 context use {name}` to select the existing one.",
            file=sys.stderr,
        )
        sys.exit(1)

    contexts = data.setdefault("contexts", {})
    block: dict[str, Any] = {"server": server}
    if app:
        block["app"] = app
    contexts[name] = block
    _write_hop3_toml(project_hop3, data)

    overlay_path = write_overlay(
        {"current": {"context": name}},
        cwd=cwd,
        home=home,
        ensure_gitignore=True,
    )

    print(f"Initialized project context {name!r}.")
    print(f"  - Added [contexts.{name}] to {project_hop3}")
    print(f"  - Wrote current context to {overlay_path}")
    if (cwd / ".gitignore").is_file() and LOCAL_OVERLAY_FILENAME in (
        cwd / ".gitignore"
    ).read_text():
        print(f"  - Ensured {LOCAL_OVERLAY_FILENAME} is in .gitignore")


def _parse_init_args(
    args: list[str],
) -> tuple[str, str, str, str | None]:
    """Parse ``--server / --app / --name`` flags for ``context init``.

    Returns ``(server, app, name, error)``. ``name`` defaults to "dev".
    """
    server = ""
    app = ""
    name = "dev"
    i = 0
    while i < len(args):
        flag = args[i]
        if flag in {"--server", "-s"}:
            if i + 1 >= len(args):
                return "", "", "", f"Error: {flag} requires a value."
            server = args[i + 1]
            i += 2
        elif flag in {"--app", "-a"}:
            if i + 1 >= len(args):
                return "", "", "", f"Error: {flag} requires a value."
            app = args[i + 1]
            i += 2
        elif flag in {"--name", "-n"}:
            if i + 1 >= len(args):
                return "", "", "", f"Error: {flag} requires a value."
            name = args[i + 1]
            i += 2
        else:
            return "", "", "", f"Unknown option: {flag}"
    return server, app, name, None


# =============================================================================
# Dispatcher
# =============================================================================


def handle_project_context(
    args: list[str],
    config: Config,
    printer: RichPrinter,
    *,
    project_hop3: Path,
    cwd: Path | None = None,
    home: Path | None = None,
) -> None:
    """Dispatch project-scoped `hop3 context` subcommands.

    Called by ``context_cmd.py:handle_context`` when CWD is inside a
    project (a hop3.toml exists in CWD or an ancestor up to $HOME).
    """
    cwd = cwd or Path.cwd()
    home = home or Path.home()

    if not args:
        # Bare `hop3 context` — show current state + subcommand list.
        _bare(project_hop3, cwd, home)
        return

    subcommand = args[0]
    sub_args = args[1:]

    handlers = {
        "list": project_context_list,
        "use": project_context_use,
        "show": project_context_show,
        "add": project_context_add,
        "remove": project_context_remove,
        "init": project_context_init,
    }
    handler = handlers.get(subcommand)
    if handler is None:
        print(
            f"Unknown context subcommand: {subcommand!r}. "
            f"Try one of: {', '.join(handlers)}.",
            file=sys.stderr,
        )
        sys.exit(1)
    handler(sub_args, project_hop3, cwd, home, printer, config)


def _bare(project_hop3: Path, cwd: Path, home: Path) -> None:
    """Bare `hop3 context` — show current state + subcommand list."""
    current = _current_context_name(cwd, home)
    contexts = _read_contexts(project_hop3)

    print(f"Project: {project_hop3}")
    if current:
        print(f"Current context: {current}")
        if current not in contexts:
            print(
                f"  warning: {current!r} is not declared in hop3.toml — "
                "did the block get removed?"
            )
    else:
        print("Current context: (none)")
        if contexts:
            print("  Use `hop3 context use <name>` to select one.")
        else:
            print("  Use `hop3 context init --server <s>` to create the first one.")

    print()
    print("Subcommands: list, use, show, add, remove, init")
    print("Run `hop3 context <subcommand> --help` for details.")
