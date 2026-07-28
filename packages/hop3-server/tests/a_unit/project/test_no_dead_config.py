# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Every hop3.toml accessor must have a caller.

`[build].build` was parsed, validated, documented — and never executed. Its
accessor (`Hop3Config.build_commands`) existed and nothing called it, so eleven
catalog apps declared build steps that silently did nothing. Nobody noticed
because their toolchain happened to do the equivalent, until one asked for
something it did not and the app shipped without the thing it exists to serve.

This is the mechanical guard against that shape: a recipe field whose value is
read by nobody is a promise the platform does not keep, and reviewing for it by
eye clearly does not work.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
PACKAGES = REPO / "packages"

#: Alternate constructors, legitimately used only by tests. They build the
#: object rather than expose a recipe field, so an absent production caller says
#: nothing about a hop3.toml field going unread.
_CONSTRUCTORS = {"from_str", "from_file", "from_dir"}

CONFIG_MODULES = {
    "packages/hop3-server/src/hop3/project/hop3_config.py": "Hop3Config",
    "packages/hop3-server/src/hop3/project/config.py": "AppConfig",
}


def _public_accessors(path: Path, classname: str) -> list[str]:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == classname:
            return [
                stmt.name
                for stmt in node.body
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not stmt.name.startswith("_")
                and stmt.name not in _CONSTRUCTORS
            ]
    msg = f"{classname} not found in {path}"
    raise AssertionError(msg)


def _sources() -> list[tuple[Path, str]]:
    """
    Production code only — deliberately NOT tests.

    This is how the original bug survived: `build_commands` had tests asserting
    it parsed correctly, so it looked covered and alive. A test exercising an
    accessor proves the parser works; it says nothing about anyone USING the
    value. Counting tests as callers would rebuild the same blind spot.
    """
    return [(path, path.read_text()) for path in PACKAGES.glob("*/src/**/*.py")]


@pytest.mark.parametrize(("module", "classname"), CONFIG_MODULES.items())
def test_every_config_accessor_is_used(module: str, classname: str) -> None:
    """
    An accessor nobody calls means a recipe field nobody reads.

    Counts callers in production code anywhere, including the defining module
    (a private helper calling it is a legitimate consumer). What must not exist
    is an accessor no shipped code path reads.
    """
    path = REPO / module
    sources = _sources()

    dead = []
    for name in _public_accessors(path, classname):
        pattern = re.compile(rf"\.{re.escape(name)}\b")
        used = any(pattern.search(text) for _, text in sources)
        if not used:
            dead.append(name)

    assert not dead, (
        f"{classname} exposes accessors nothing calls, so the hop3.toml fields "
        f"behind them are read by nobody: {dead}. Either wire them up or delete "
        f"them — a field the platform parses and ignores is a promise it does "
        f"not keep (see [build].build)."
    )
