# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
What the server's commands document and read, against what the client sends.

The client parses argv before the server sees it: it keeps its own flags
(``--app``, ``--dry-run``, ``--force``, ``-d``, ``-q``, ``-v``...), expands
aliases, and forwards ``--app`` only to the commands it knows are app-scoped.
Nothing tied the two sides together, and they drifted in ways users saw:
`hop3 addon list --app x` was refused, `hop3 addon promote` could not be run
at all, `hop3 cert renew --force` renewed only the certs already due, and
`hop3 system cleanup --dry-run` pruned for real.

Skipped whole when hop3-server is absent, so a standalone hop3-cli install has
nothing to compare against; in the workspace, where both are present, it runs.
"""

from __future__ import annotations

import inspect
import re
import shlex
from pathlib import Path

import pytest
from hop3_cli.commands.flags import parse_flags
from hop3_cli.commands.local import is_local_command
from hop3_cli.core.aliases import CORE_ALIASES
from hop3_cli.core.app_scope import APP_SCOPED_COMMANDS, is_app_scoped

pytest.importorskip("hop3.commands.app", reason="hop3-server is not installed")

from hop3.commands._base import Command, NamespaceCommand
from hop3.commands._help_render import parse_docstring_sections
from hop3.lib.args import parse_cli_args
from hop3.server.controllers.rpc import commands, find_command

#: Server commands the client never sends: `hop3-server git-hook` runs on the
#: box, from the post-receive hook.
NOT_SENT_BY_THE_CLIENT = {("git-hook",)}

#: Client flags that reach the server anyway: `--dry-run` is handed back to
#: every command but `deploy` (`_forward_dry_run`).
FORWARDED = {"--dry-run"}

REPO = Path(__file__).resolve().parents[5]

#: Pages whose command lines are not the current CLI: ADRs record proposals,
#: blog posts are dated, and docs/src/tutorials is generated from docs/tutorials.
UNCHECKED_DOCS = ("docs/src/developers/adrs/", "docs/src/blog/", "docs/src/tutorials/")

#: Lines wrong on purpose: the cheat sheet shows the did-you-mean hint.
DELIBERATE_TYPOS = {"hop3 deplo --app myapp"}

_READ_IN_ARGS = re.compile(r'"(--?[a-z][a-z-]*)" in args')
_SHELL_OPERATORS = re.compile(r"\s(?:&&|\|\||\||;|>>|2?>|<)\s")
_ALIASES = {alias.source_token: list(alias.expansion) for alias in CORE_ALIASES}


def _command_classes() -> list[type[Command]]:
    unique = {id(cmd): cmd for cmd in commands.values()}
    return sorted(unique.values(), key=lambda cmd: cmd.name)


def _call_source(cmd: type[Command]) -> str:
    try:
        return inspect.getsource(cmd)
    except (OSError, TypeError):
        return ""


def _reads_app_flag(cmd: type[Command]) -> bool:
    spec = getattr(cmd, "_arg_spec", {}) or {}
    if "app" in spec and not spec["app"].get("positional"):
        return True
    source = _call_source(cmd)
    return "_resolve_app(" in source or "pop_app_flag(" in source


def _flags_read(cmd: type[Command]) -> set[str]:
    """Every option token the command reads: its spec, and `"--x" in args`."""
    spec = getattr(cmd, "_arg_spec", {}) or {}
    flags = set(_READ_IN_ARGS.findall(_call_source(cmd)))
    for key, option in spec.items():
        if option.get("positional") or option.get("remaining"):
            continue
        flags.add("--" + key.replace("_", "-"))
        if "short" in option:
            flags.add(option["short"])
    return flags


def _documented_invocations(cmd: type[Command]) -> list[str]:
    """The `hop3 ...` command lines of a docstring's Usage and Examples."""
    sections = parse_docstring_sections(cmd.__doc__)
    lines = []
    for line in sections["usage"] + sections["examples"]:
        command_line = line.split("  #")[0].rstrip("\\ ")
        for piece in _SHELL_OPERATORS.split(command_line):
            piece = piece.strip()
            if piece.startswith("hop3 "):
                lines.append(piece)
    return lines


def test_every_server_flag_survives_the_client() -> None:
    """
    A flag the client keeps for itself never reaches the server.

    `cert renew --force` became a confirmation skip, `system info -v` a
    verbosity level, `catalog install -d <host>` a debug flag: each command
    read a flag it could never receive.
    """
    swallowed = []
    for cmd in _command_classes():
        for flag in sorted(_flags_read(cmd) - FORWARDED - {"--app", "-a"}):
            _, rest = parse_flags(["x", flag, "value"])
            if flag not in rest:
                swallowed.append(f"{' '.join(cmd.name)} {flag}")
    assert not swallowed, (
        f"the client consumes these flags before the server can read them; "
        f"rename them or read what the client forwards: {swallowed}"
    )


def test_every_server_command_reading_app_is_in_the_allowlist() -> None:
    """
    A command that reads --app must be listed client-side, or it breaks.

    `parse_flags` strips a typed `--app` into `flags.app`, and only app-scoped
    commands get it back; every other command refuses it.
    """
    missing = [
        cmd.name
        for cmd in _command_classes()
        if _reads_app_flag(cmd)
        and cmd.name not in NOT_SENT_BY_THE_CLIENT
        and cmd.name not in APP_SCOPED_COMMANDS
    ]
    assert not missing, (
        f"these commands read --app server-side but are absent from "
        f"APP_SCOPED_COMMANDS, so the CLI refuses their --app flag: {missing}"
    )


def test_every_documented_invocation_reaches_its_command() -> None:
    """
    Each `hop3 ...` line in a docstring is one the client and server accept.

    It must name a command (after the client's aliases), carry --app only
    where the client forwards it, and, when it has no placeholder, parse
    under the command's own argument spec.
    """
    broken = []
    for cmd in _command_classes():
        if cmd.name in NOT_SENT_BY_THE_CLIENT:
            continue
        for line in _documented_invocations(cmd):
            problem = _invocation_problem(line)
            if problem:
                broken.append(f"{' '.join(cmd.name)}: `{line}`: {problem}")
    assert not broken, "\n".join(broken)


def _invocation_problem(line: str) -> str | None:
    """Why the client or the server would not run ``line``, or None."""
    flags, argv = parse_flags(shlex.split(line)[1:])
    if argv and argv[0] in _ALIASES:
        argv = _ALIASES[argv[0]] + argv[1:]
    if is_local_command(argv) or {"--help", "-h"} & set(argv):
        return None
    target, consumed = find_command(argv)
    if target is None:
        return "no such command"
    rest = argv[consumed:]
    if issubclass(target, NamespaceCommand) and rest:
        return f"no `{' '.join(target.name)} {rest[0]}` command"
    if flags.app and not is_app_scoped(argv)[0]:
        return "the client refuses --app for this command"
    return _server_problem(target, rest, flags.app, line)


def _server_problem(
    target: type[Command], rest: list[str], app: str | None, line: str
) -> str | None:
    """Why ``target``'s argument spec rejects ``rest``, or None."""
    spec = getattr(target, "_arg_spec", None)
    if not spec or any(ch in line for ch in "<[("):
        return None
    if app and "app" in spec:
        rest = [*rest, "--app", app]
    try:
        parse_cli_args(rest, spec)
    except ValueError as exc:
        return str(exc)
    return None


def test_every_invocation_in_the_docs_is_accepted() -> None:
    """
    The guides and tutorials teach commands the CLI and server run.

    Fifteen tutorial lines taught `hop3 addon attach <app> <addon>`, nine a
    `--tail` that `app logs` never had, and six `hop3 backup list <app>`.
    """
    pages = [
        page
        for root in ("docs/src", "docs/tutorials")
        for page in sorted((REPO / root).rglob("*.md"))
        if not str(page.relative_to(REPO)).startswith(UNCHECKED_DOCS)
    ]
    assert pages, f"no documentation under {REPO}"
    broken = []
    for page in pages:
        for number, line in _code_block_invocations(page):
            if line in DELIBERATE_TYPOS:
                continue
            problem = _invocation_problem(line)
            if problem:
                where = f"{page.relative_to(REPO)}:{number}"
                broken.append(f"{where}: `{line}`: {problem}")
    assert not broken, "\n".join(broken)


def _code_block_invocations(page: Path) -> list[tuple[int, str]]:
    """The `hop3 ...` command lines inside a page's fenced code blocks."""
    found = []
    in_code = False
    for number, raw in enumerate(page.read_text().splitlines(), 1):
        if raw.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            continue
        line = re.sub(r"^\s*[$❯]\s*", "", raw)
        line = line.split(" # ")[0].split("  #")[0].rstrip("\\ ").strip()
        for piece in _SHELL_OPERATORS.split(line):
            piece = piece.strip()
            if piece.startswith("hop3 "):
                found.append((number, piece))
    return found


def test_every_usage_line_names_its_command() -> None:
    """`hop3 user show`'s usage said `hop3 user info`, a command that never was."""
    wrong = []
    for cmd in _command_classes():
        names = [cmd.name, *getattr(cmd, "aliases", [])]
        prefixes = tuple(f"hop3 {' '.join(name)}" for name in names)
        for line in parse_docstring_sections(cmd.__doc__)["usage"]:
            if line.startswith("hop3 ") and not line.startswith(prefixes):
                wrong.append(f"{' '.join(cmd.name)}: {line}")
    assert not wrong, wrong


def test_every_usage_error_has_a_usage_to_show() -> None:
    """`usage_error()` reads the docstring's Usage block; an empty one says nothing."""
    empty = [
        cmd.name
        for cmd in _command_classes()
        if "usage_error(" in _call_source(cmd)
        and not parse_docstring_sections(cmd.__doc__)["usage"]
    ]
    assert not empty, f"these commands raise usage_error() with no Usage: {empty}"
