# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Every command the TUI sends must exist on the server.

The TUI is a thin client over hop3-server's own CLI surface: it posts an argv to the
one `cli` JSON-RPC method. Nothing checks that the argv it builds names a command the
server actually registers, so the whole surface can rot silently — and it has. The
client's own tests only ever asserted the parsing of canned responses, which is why
a `["config", "show", app]` against a server whose namespace is `env` looked fine.

This reads both sides out of the source with `ast` rather than importing them:
hop3-tui does not depend on hop3-server and must not start, and the coupling being
checked is "these two agree on a vocabulary", not a call graph.

An end-to-end test would catch this too, and catch more. This is the cheap, hermetic
part of that job, and it runs in the fast lane.
"""

from __future__ import annotations

import ast
from pathlib import Path

import hop3_tui
import pytest

TUI_CLIENT = Path(hop3_tui.__file__).resolve().parent / "api" / "client.py"
SERVER_COMMANDS = Path(__file__).resolve().parents[3] / "hop3-server/src/hop3/commands"

#: Commands the client sends that the server does not register. Empty, and meant to
#: stay that way: it exists so a deliberate, documented gap can be recorded without
#: disabling the check for everything else.
KNOWN_BROKEN: dict[tuple[str, ...], str] = {}


def _server_command_names() -> set[tuple[str, ...]]:
    """Every command name the server registers, canonical spellings and aliases.

    A command declares `name: ClassVar[tuple[str, ...]]` and may declare
    `aliases: ClassVar[list[tuple[str, ...]]]`. Both are addressable — `config set`
    is an alias of `env set` — so reading only `name` under-reports what the server
    accepts, which is a false alarm rather than a missed bug, but still wrong.
    """
    names: set[tuple[str, ...]] = set()
    for path in sorted(SERVER_COMMANDS.glob("*.py")):
        tree = ast.parse(path.read_text(), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AnnAssign) or node.value is None:
                continue
            target = node.target
            if not isinstance(target, ast.Name):
                continue
            if target.id == "name" and isinstance(node.value, ast.Tuple):
                if parts := _words(node.value):
                    names.add(parts)
            elif target.id == "aliases" and isinstance(node.value, ast.List):
                for element in node.value.elts:
                    if isinstance(element, ast.Tuple) and (parts := _words(element)):
                        names.add(parts)
    return names


def _words(node: ast.Tuple) -> tuple[str, ...]:
    """The string literals of a tuple node, in order."""
    return tuple(
        element.value
        for element in node.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    )


def _tui_commands() -> list[tuple[str, tuple[str, ...]]]:
    """Each `_rpc_call([...])` in the client, as (method, leading literal words).

    Only the leading string literals are the command name; everything after the
    first interpolated argument is a value, not vocabulary.
    """
    tree = ast.parse(TUI_CLIENT.read_text(), str(TUI_CLIENT))
    found: list[tuple[str, tuple[str, ...]]] = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            callee = node.func
            if not (isinstance(callee, ast.Attribute) and callee.attr == "_rpc_call"):
                continue
            if not isinstance(node.args[0], ast.List):
                continue
            words: list[str] = []
            for element in node.args[0].elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    if element.value.startswith("-"):
                        break
                    words.append(element.value)
                else:
                    break
            if words:
                found.append((function.name, tuple(words)))
    return found


def _resolves(words: tuple[str, ...], registry: set[tuple[str, ...]]) -> bool:
    """The command name must be registered exactly.

    Not a prefix: `("app", "deploy")` is not valid merely because `("app",)` is a
    registered namespace — the server would reject the unknown subcommand. Matching
    on prefixes is what let three broken commands look fine here.
    """
    return words in registry


@pytest.fixture(scope="module")
def registry() -> set[tuple[str, ...]]:
    if not SERVER_COMMANDS.is_dir():
        pytest.fail(
            f"hop3-server's commands are not at {SERVER_COMMANDS}. This test compares "
            "two packages in the same workspace; if the layout moved, fix the path "
            "rather than skipping — a silently skipped contract check is worthless."
        )
    names = _server_command_names()
    assert len(names) > 50, f"only parsed {len(names)} server commands; parser broke"
    return names


def test_the_client_builds_commands_this_test_can_read():
    """Guard the parser itself: a regex that matches nothing would pass everything."""
    commands = _tui_commands()

    assert len(commands) > 20, f"only found {len(commands)} client calls"
    assert ("list_apps", ("app", "list")) in commands


def test_no_new_command_drifts_away_from_the_server(registry):
    """The ratchet: anything broken beyond `KNOWN_BROKEN` fails here and now."""
    broken = {
        words
        for _, words in _tui_commands()
        if not _resolves(words, registry) and words not in KNOWN_BROKEN
    }

    assert not broken, (
        f"these commands do not exist on the server: {sorted(broken)}. Either fix the "
        f"argv in hop3_tui/api/client.py or, if the server dropped the command, say so "
        f"in KNOWN_BROKEN."
    )


def test_a_known_broken_command_that_got_fixed_is_removed_from_the_list(registry):
    """So the list shrinks to nothing instead of being carried forever."""
    fixed = {words for words in KNOWN_BROKEN if _resolves(words, registry)}

    assert not fixed, (
        f"{sorted(fixed)} now resolve on the server — delete them from KNOWN_BROKEN."
    )


def test_every_command_the_tui_sends_exists_on_the_server(registry):
    """The whole point. Was xfail until the client was rewritten against hop3-cli."""
    unknown = [
        (method, words)
        for method, words in _tui_commands()
        if not _resolves(words, registry)
    ]

    assert not unknown, (
        f"{len(unknown)} commands the server does not register: {unknown}"
    )


#: Client methods whose command is app-scoped on the server, i.e. whose handler calls
#: `_resolve_app`. Derived by reading the server's commands, not guessed.
APP_SCOPED = {
    "get_app",
    "start_app",
    "stop_app",
    "restart_app",
    "delete_app",
    "get_app_logs",
    "get_env_vars",
    "set_env_var",
    "delete_env_var",
}


def test_an_app_scoped_command_passes_the_app_as_a_flag():
    """ADR 036 D5. Was xfail until the client was rewritten against hop3-cli."""
    tree = ast.parse(TUI_CLIENT.read_text(), str(TUI_CLIENT))
    positional = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if function.name not in APP_SCOPED:
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            callee = node.func
            if not (isinstance(callee, ast.Attribute) and callee.attr == "_rpc_call"):
                continue
            if not isinstance(node.args[0], ast.List):
                continue
            flags = [
                element.value
                for element in node.args[0].elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
            if "--app" not in flags:
                positional.append(function.name)

    assert not positional, (
        f"{len(positional)} app-scoped commands pass the app name positionally: "
        f"{sorted(positional)}"
    )
