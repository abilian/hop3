# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""ADR-036 consistency renames: the new canonical name and the old name (kept as
a back-compat alias) must both resolve to the same command class."""

from __future__ import annotations

import pytest

from hop3.server.controllers import rpc

# (new canonical, old alias) — both must dispatch to the same class.
RENAMES = [
    (("app", "create"), ("app", "launch")),
    (("user", "add"), ("auth", "register")),  # P2.1: auth register folded into user add
    (("backup", "show"), ("backup", "info")),
    (("app", "migrate"), ("env", "migrate")),
    (("app", "migrate"), ("config", "migrate")),
    (("addon", "postgres", "activity"), ("addon", "postgres", "ps")),
    (("addon", "mysql", "activity"), ("addon", "mysql", "ps")),
    (("domain",), ("domains",)),
    (("domain", "add"), ("domains", "add")),
    (("domain", "list"), ("domains", "list")),
    (("domain", "remove"), ("domains", "remove")),
    (("domain", "set"), ("domains", "set")),
    (("domain", "clear"), ("domains", "clear")),
]


@pytest.mark.parametrize(("canonical", "alias"), RENAMES)
def test_rename_keeps_old_path_working(canonical, alias):
    table = rpc._commands
    assert canonical in table, f"new canonical {canonical} not registered"
    assert alias in table, f"back-compat alias {alias} not registered"
    assert table[canonical] is table[alias], (
        f"{alias} should dispatch to the same class as {canonical}"
    )


def test_old_names_resolve_via_find_command():
    # The longest-prefix resolver still matches the old paths (with trailing arg).
    cmd, n = rpc.find_command(["backup", "info", "20251030_x"])
    assert cmd is rpc._commands["backup", "show"]
    assert n == 2
    cmd, n = rpc.find_command(["app", "launch", "repo", "myapp"])
    assert cmd is rpc._commands["app", "create"]
