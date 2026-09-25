# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Every command's minimum role matches the checked-in table (ADR 061 §3).

The table, ``command_roles.toml`` beside this file, is the whole authorization
policy in one reviewable place: a change to who can run what must show up as a
diff to it. A new command without a declaration defaults to ``admin``, and this
test then fails until the table says so on purpose.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import tomllib

from hop3.core.roles import Role
from hop3.server.controllers.rpc import commands, format_command_name

TABLE = tomllib.loads((Path(__file__).parent / "command_roles.toml").read_text())
REGISTERED = {format_command_name(cls.name): cls for cls in commands.values()}


def test_every_command_is_listed_exactly_once():
    listed = Counter(name for names in TABLE.values() for name in names)

    assert [name for name, count in listed.items() if count > 1] == []
    assert sorted(REGISTERED.keys() - listed.keys()) == []
    assert sorted(listed.keys() - REGISTERED.keys()) == []


@pytest.mark.parametrize("name", sorted(TABLE["public"]))
def test_public_commands_need_no_token(name: str):
    assert REGISTERED[name].requires_auth is False


@pytest.mark.parametrize(
    ("name", "role"),
    [
        (name, Role(section))
        for section, names in TABLE.items()
        if section != "public"
        for name in names
    ],
)
def test_each_command_declares_its_role(name: str, role: Role):
    command = REGISTERED[name]
    assert command.requires_auth is True
    assert command.min_role is role
