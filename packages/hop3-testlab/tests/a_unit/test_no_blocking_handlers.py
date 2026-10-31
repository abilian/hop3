# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
No async web handler does its work on the event loop.

The Test Lab serves on one event loop. Dishka's ``@inject`` wraps coroutines
only, so every injected handler is an ``async def``; a repository query, a
``session.commit()``, a file read or a signal sent from its body runs on the
loop and freezes every other request (a SQLite lock wait included). The
convention, as in hop3-server: the handler's body is one
``return await anyio.to_thread.run_sync(self._work, arg, ...)`` and the sync
``_work`` does the I/O, the commit and builds the response.

Checked on the source: an ``async def`` in a controller module may hold a
docstring and that single statement, whose arguments are plain names or
attributes (nothing evaluated on the loop).
"""

from __future__ import annotations

import ast
from pathlib import Path

import hop3_testlab.web.controllers as controllers_pkg
import pytest

CONTROLLERS_DIR = Path(controllers_pkg.__file__).parent
CONTROLLER_FILES = sorted(CONTROLLERS_DIR.glob("*.py"))


def _is_run_sync(node: ast.expr) -> bool:
    """``anyio.to_thread.run_sync`` (the spelling the controllers import)."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "run_sync"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "to_thread"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "anyio"
    )


def _offloads_everything(func: ast.AsyncFunctionDef) -> bool:
    body = func.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
    ):
        body = body[1:]  # docstring
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    awaited = body[0].value
    if not isinstance(awaited, ast.Await) or not isinstance(awaited.value, ast.Call):
        return False
    call = awaited.value
    args = [*call.args, *(kw.value for kw in call.keywords)]
    return _is_run_sync(call.func) and all(
        isinstance(arg, ast.Name | ast.Attribute) for arg in args
    )


def loop_bound_handlers(source: str) -> list[str]:
    """Names of the ``async def``s in ``source`` that do work on the loop."""
    return [
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AsyncFunctionDef) and not _offloads_everything(node)
    ]


@pytest.mark.parametrize("path", CONTROLLER_FILES, ids=lambda p: p.name)
def test_async_handlers_offload_to_a_thread(path: Path) -> None:
    offenders = loop_bound_handlers(path.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{path.name}: {offenders} run work on the event loop. Make the body "
        "`return await anyio.to_thread.run_sync(self._work, args...)` and do "
        "the repository/session/file work (and the commit) in the sync `_work`."
    )


def test_the_check_sees_the_controllers() -> None:
    sources = "".join(p.read_text(encoding="utf-8") for p in CONTROLLER_FILES)
    assert sources.count("async def ") >= 20


@pytest.mark.parametrize(
    "body",
    [
        "session.commit()\n        return await anyio.to_thread.run_sync(self._x, a)",
        "return await anyio.to_thread.run_sync(self._x, runs.list_all())",
        "return Template(template_name='x', context=_ctx(runs))",
        "x = await anyio.to_thread.run_sync(self._x, a)\n        return x",
    ],
)
def test_it_flags_work_on_the_loop(body: str) -> None:
    source = (
        f"class C:\n    async def handler(self, a, runs, session):\n        {body}\n"
    )
    assert loop_bound_handlers(source) == ["handler"]


def test_it_accepts_the_convention() -> None:
    source = (
        "class C:\n"
        "    async def handler(self, a, runs):\n"
        '        """Doc."""\n'
        "        return await anyio.to_thread.run_sync(self._x, runs, a)\n"
    )
    assert loop_bound_handlers(source) == []
