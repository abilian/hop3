# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`hop3 context` — the servers you can reach, and which one this checkout uses.

A context is a server, global and personal (ADR 042): it lives in
``~/.config/hop3-cli/config.toml`` and never in ``hop3.toml``. What is local
is the **binding**: ``.hop3-local.toml`` beside a project's ``hop3.toml``,
gitignored, written only by ``hop3 context use``. Verbs:

- bare / ``list`` / ``show``  — read contexts, and where a command here goes
- ``add`` / ``remove`` / ``rename`` — edit contexts in config.toml
- ``use`` / ``unset``          — inside a project, bind or unbind this
  checkout; outside one (or with ``--global``), set or clear the global
  current context. Both ask first, naming the scope; ``--yes`` skips it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from hop3_cli.commands.local.help_text import print_context_help
from hop3_cli.config import ENV_CONTEXT_NAME
from hop3_cli.core.hop3_toml import first_hop3_toml, read_hop3_toml
from hop3_cli.core.local_overlay import (
    LOCAL_OVERLAY_FILENAME,
    atomic_write_toml,
    read_binding,
    read_overlay,
    write_overlay,
)
from hop3_cli.core.target import check_project_blocks
from hop3_cli.exceptions import TargetError
from hop3_cli.exit_codes import ExitCode
from hop3_cli.ui.prompts import is_no_input

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter

# Context names flow into TOML keys; keep them shell-friendly (same shape as the
# server-side validator in project/schema.py).
_CONTEXT_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

_SUBCOMMANDS = "list, show, add, remove, rename, use, unset"


def handle_context(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Dispatch `hop3 context <subcommand>` (ADR 042)."""
    if args and args[0] in {"--help", "-h"}:
        print_context_help()
        return
    if not args:
        _context_bare(config)
        return

    subcommand, sub_args = args[0], args[1:]
    handlers = {
        "list": lambda: context_list(config),
        "show": lambda: context_show(sub_args, config),
        "add": lambda: context_add(sub_args, config),
        "remove": lambda: context_remove(sub_args, config),
        "rename": lambda: context_rename(sub_args, config),
        "use": lambda: context_use(sub_args, config),
        "unset": lambda: context_unset(sub_args, config),
    }
    handler = handlers.get(subcommand)
    if handler is None:
        print(f"Unknown context subcommand: {subcommand}", file=sys.stderr)
        print_context_help()
        sys.exit(ExitCode.USAGE_ERROR)
    handler()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _fail(message: str, code: int = ExitCode.USAGE_ERROR) -> NoReturn:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(code)


def _project_dir() -> Path | None:
    """The directory of the nearest hop3.toml at or above the CWD, or None."""
    path, _ = first_hop3_toml(Path.cwd(), Path.home())
    return path.parent if path is not None else None


def _positionals(args: list[str]) -> list[str]:
    return [a for a in args if not a.startswith("-")]


def _is_global(args: list[str]) -> bool:
    return "--global" in args or "-g" in args


def _known_contexts(config: Config) -> dict[str, str]:
    """Contexts the operator defined (the environment's ``env`` excluded)."""
    return {
        name: server
        for name, server in config.list_global_contexts().items()
        if name != ENV_CONTEXT_NAME
    }


def _require_known(name: str, config: Config) -> str:
    """The server of context ``name``, or exit naming the known ones."""
    server = _known_contexts(config).get(name)
    if server is None:
        known = ", ".join(sorted(_known_contexts(config))) or "(none)"
        _fail(
            f"context {name!r} is not defined (known: {known}).\n"
            f"  Define it: hop3 context add {name} --server <address>",
            ExitCode.RESOLUTION_ERROR,
        )
    return server


def _confirm(question: str, config: Config) -> None:
    """Ask before writing; ``--yes`` skips it, and no terminal refuses."""
    if config.assume_yes():
        return
    if is_no_input() or not sys.stdin.isatty():
        _fail(
            f"{question}\n  Refusing to change it without a terminal: re-run "
            "with --yes.",
            ExitCode.CONFIRMATION_DECLINED,
        )
    if input(f"{question} [y/N] ").strip().lower() not in {"y", "yes"}:
        print("Unchanged.", file=sys.stderr)
        sys.exit(ExitCode.CONFIRMATION_DECLINED)


def _project_blocks(project_dir: Path) -> dict[str, dict[str, Any]]:
    contexts = read_hop3_toml(project_dir / "hop3.toml").get("contexts")
    if not isinstance(contexts, dict):
        return {}
    return {k: v for k, v in contexts.items() if isinstance(v, dict)}


# --------------------------------------------------------------------------
# Read commands: bare / list / show
# --------------------------------------------------------------------------


def _where_here(config: Config) -> str:
    """Where a command run here goes, and why — or why it goes nowhere."""
    try:
        target = config.require_target()
    except TargetError as e:
        return f"Here: {e}"
    return f"Here: {target.context} ({target.server}), {target.source.value}"


def _context_bare(config: Config) -> None:
    print(_where_here(config))
    contexts = _known_contexts(config)
    if contexts:
        print()
        _print_contexts(config, contexts)
    print(f"\nSubcommands: {_SUBCOMMANDS}. Run `hop3 context --help` for details.")


def _print_contexts(config: Config, contexts: dict[str, str]) -> None:
    here = config.get_current_context_name()
    default = config.get_default_context()
    for name in sorted(contexts):
        marker = "*" if name == here else " "
        note = "  (global current context)" if name == default else ""
        print(f"  {marker} {name:<12} {contexts[name]}{note}")


def context_list(config: Config) -> None:
    """List contexts; ``*`` marks the one a command here would use."""
    contexts = _known_contexts(config)
    if not contexts:
        print("No contexts defined. Sign in to a server to create one:")
        print("  hop3 login <user>@<host>")
        print("  hop3 context add prod --server https://hop3.example.com")
        return
    _print_contexts(config, contexts)
    print(f"\n{_where_here(config)}")


def context_show(args: list[str], config: Config) -> None:
    """Show one context: its addresses and, in a project, its block."""
    positional = _positionals(args)
    name = positional[0] if positional else config.get_current_context_name()
    if not name:
        print(_where_here(config))
        return
    server = _require_known(name, config)
    print(f"Context: {name}")
    print(f"  server:     {server}")
    if bootstrap := config.get_context_bootstrap(name):
        print(f"  bootstrap:  {bootstrap}")
    if name == config.get_default_context():
        print("  the global current context")
    project_dir = _project_dir()
    if project_dir is None:
        return
    if read_binding(project_dir) == name:
        print(f"  bound to this checkout ({project_dir})")
    block = _project_blocks(project_dir).get(name)
    if block is not None:
        _print_block(name, block)


def _print_block(name: str, block: dict[str, Any]) -> None:
    print(f"  [contexts.{name}] in hop3.toml:")
    if block.get("app"):
        print(f"    app:      {block['app']}")
    domains = block.get("domains")
    if isinstance(domains, dict) and domains.get("list"):
        print(f"    domains:  {', '.join(map(str, domains['list']))}")
    if isinstance(block.get("env"), dict) and block["env"]:
        print(f"    env:      {', '.join(sorted(block['env']))}")


# --------------------------------------------------------------------------
# Write commands: add / remove / rename (config.toml)
# --------------------------------------------------------------------------


_ADD_USAGE = """Usage: hop3 context add <name> --server <address> [--bootstrap ssh://…]

Names a server you can reach, in ~/.config/hop3-cli/config.toml. The token
stays in the credential store; `hop3 login` creates a context too.

--bootstrap is the ssh:// route used ONLY to renew an expired token. It lets
an https:// server renew unattended; omit it when the server is itself ssh://.

What the app is called on that server, its domains and its environment belong
in the project's hop3.toml, as a [contexts.<name>] block."""


def _parse_add_args(args: list[str]) -> tuple[str, str]:
    """Parse `--server` and `--bootstrap` for `context add`."""
    server = ""
    bootstrap = ""
    i = 0
    while i < len(args):
        flag = args[i]
        if flag in {"--server", "-s"} and i + 1 < len(args):
            server = args[i + 1]
        elif flag == "--bootstrap" and i + 1 < len(args):
            bootstrap = args[i + 1]
        elif flag in {"--domain", "--domains", "--env"}:
            _fail(
                f"{flag} belongs to the project: write it in hop3.toml, under "
                "[contexts.<name>]. A context only names a server."
            )
        else:
            _fail(f"unknown or incomplete option: {flag}\n\n{_ADD_USAGE}")
        i += 2
    return server, bootstrap


def context_add(args: list[str], config: Config) -> None:
    """Add a context to config.toml: a name for a server."""
    if not args or args[0] in {"--help", "-h"}:
        print(_ADD_USAGE)
        return

    name = args[0]
    if not _CONTEXT_NAME_RE.fullmatch(name):
        _fail(f"invalid context name {name!r}: letters/digits then -/_ , max 64.")
    if name == ENV_CONTEXT_NAME:
        _fail(f"{name!r} is reserved for the target HOP3_API_URL names.")
    if config.get_app_override():
        _fail(
            "--app belongs to the project: write it in hop3.toml, as "
            f'[contexts.{name}] app = "…". A context only names a server.'
        )
    # Every context is global; `--global` is accepted and changes nothing.
    server, bootstrap = _parse_add_args([
        a for a in args[1:] if a not in {"--global", "-g"}
    ])
    if not server:
        _fail(f"--server <address> is required.\n\n{_ADD_USAGE}")
    if bootstrap and not bootstrap.startswith("ssh://"):
        _fail(f"--bootstrap must be an ssh:// address, got {bootstrap!r}.")
    if name in _known_contexts(config):
        _fail(
            f"context {name!r} already exists. Remove it first: "
            f"hop3 context remove {name}"
        )

    config.set_context_server(name, server, bootstrap=bootstrap or None)
    print(f"Added context {name!r}: {server}")
    if bootstrap:
        print(f"  token renewal over {bootstrap}")
    print(f"  use it here: hop3 context use {name}   or once: hop3 -c {name} …")


def context_remove(args: list[str], config: Config) -> None:
    """Remove a context from config.toml."""
    positional = _positionals(args)
    if not positional:
        _fail("usage: hop3 context remove <name>")
    name = positional[0]
    if not config.remove_global_context(name):
        _fail(f"context {name!r} is not defined.", ExitCode.RESOLUTION_ERROR)
    print(f"Removed context {name!r}.")
    project_dir = _project_dir()
    if project_dir is not None and read_binding(project_dir) == name:
        print(
            f"  this checkout is still bound to {name!r}, so its commands are "
            "refused until you bind another: hop3 context use <name>"
        )


def context_rename(args: list[str], config: Config) -> None:
    """Rename a context; the global current context and this binding follow."""
    positional = _positionals(args)
    if len(positional) < 2:
        _fail("usage: hop3 context rename <old> <new>")
    old, new = positional[0], positional[1]
    _require_known(old, config)
    if not _CONTEXT_NAME_RE.fullmatch(new) or new == ENV_CONTEXT_NAME:
        _fail(f"invalid context name {new!r}.")
    if new in _known_contexts(config):
        _fail(f"context {new!r} already exists.")

    config.rename_context(old, new)
    print(f"Renamed context {old!r} to {new!r}.")
    project_dir = _project_dir()
    if project_dir is None:
        return
    if read_binding(project_dir) == old:
        write_overlay({"local": {"context": new}}, cwd=project_dir, home=project_dir)
        print(f"  this checkout is now bound to {new!r}.")
    if old in _project_blocks(project_dir):
        print(
            f"  hop3.toml has a [contexts.{old}] block: it applies only to a "
            f"context named {old!r}, so rename the block too, or keep the old name."
        )


# --------------------------------------------------------------------------
# Selection: use / unset (the binding, or the global current context)
# --------------------------------------------------------------------------


def context_use(args: list[str], config: Config) -> None:
    """
    Bind this checkout to a context, or set the global current context.

    Inside a project the binding is written; outside one, or with
    ``--global``, the global current context. Either way the question names
    the scope, the file and the address before anything is written.
    """
    positional = _positionals(args)
    if not positional:
        _fail("usage: hop3 context use [--global] <name>")
    name = positional[0]
    server = _require_known(name, config)
    project_dir = _project_dir()

    if project_dir is None or _is_global(args):
        _use_global(name, server, config, inside_project=project_dir is not None)
        return

    try:
        check_project_blocks(project_dir / "hop3.toml", name)
    except TargetError as e:
        _fail(str(e), ExitCode.RESOLUTION_ERROR)
    if read_binding(project_dir) == name:
        print(f"This checkout is already bound to {name!r} ({server}).")
        return
    question = f"Bind this checkout ({project_dir}) to {name!r} ({server})?"
    if config.is_context_protected(name):
        question += (
            "\n  It is protected: a change still needs -c or HOP3_CONTEXT, and the "
            "app's name typed."
        )
    _confirm(question, config)
    write_overlay({"local": {"context": name}}, cwd=project_dir, home=project_dir)
    print(
        f"Bound {project_dir} to {name!r}, in {LOCAL_OVERLAY_FILENAME} (not committed)."
    )


def _use_global(
    name: str, server: str, config: Config, *, inside_project: bool
) -> None:
    if config.get_default_context() == name:
        print(f"The global current context is already {name!r} ({server}).")
        return
    _confirm(f"Set the global context to {name!r} ({server})?", config)
    config.set_default_context(name)
    print(f"Global context: {name!r} ({server}).")
    if inside_project:
        print("  inside this checkout, its binding still decides where commands go.")


def context_unset(args: list[str], config: Config) -> None:
    """Remove this checkout's binding, or the global current context."""
    project_dir = _project_dir()
    if project_dir is None or _is_global(args):
        current = config.get_default_context()
        if not current:
            print("There is no global current context.")
            return
        _confirm(f"Clear the global context ({current!r})?", config)
        config.set_default_context(None)
        print(f"Cleared the global context (was {current!r}).")
        return

    bound = read_binding(project_dir)
    if not bound:
        print(f"This checkout ({project_dir}) is not bound to a context.")
        return
    _confirm(f"Unbind this checkout ({project_dir}) from {bound!r}?", config)
    _remove_binding(project_dir)
    print(
        f"Unbound {project_dir} from {bound!r}: its commands are refused until "
        "you bind it again."
    )


def _remove_binding(project_dir: Path) -> None:
    """Drop the binding from the overlay; delete the file when nothing is left."""
    overlay = read_overlay(cwd=project_dir, home=project_dir)
    if overlay.path is None:
        return
    data = {
        section: {k: v for k, v in block.items() if k != "context"}
        if section in {"local", "current"} and isinstance(block, dict)
        else block
        for section, block in overlay.data.items()
    }
    data = {k: v for k, v in data.items() if v != {}}
    if data:
        atomic_write_toml(overlay.path, data)
    else:
        overlay.path.unlink()
