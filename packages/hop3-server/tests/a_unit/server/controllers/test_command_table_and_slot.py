# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The dispatch table refuses a name collision; the command slot waits bounded."""

from __future__ import annotations

from typing import ClassVar

import anyio
import pytest

from hop3.commands import Command
from hop3.server.controllers.rpc import (
    CommandSlot,
    ServerBusyError,
    build_command_table,
)


class _Status(Command):
    name: ClassVar[tuple[str, ...]] = ("app", "status")


class _PluginStatus(Command):
    name: ClassVar[tuple[str, ...]] = ("app", "state")
    aliases: ClassVar[list[tuple[str, ...]]] = [("app", "status")]


def test_a_name_claimed_twice_aborts_the_table_build():
    with pytest.raises(RuntimeError, match=r"'hop3 app status' is claimed by both"):
        build_command_table([_Status, _PluginStatus])


def test_the_same_command_listed_twice_is_not_a_collision():
    table = build_command_table([_Status, _Status])

    assert table == {("app", "status"): _Status}


@pytest.mark.anyio
async def test_a_second_call_is_told_which_command_holds_the_slot():
    slot = CommandSlot(wait_seconds=0.05)
    holding = anyio.Event()
    release = anyio.Event()

    async def run_backup() -> None:
        async with slot.hold("backup create"):
            holding.set()
            await release.wait()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_backup)
        await holding.wait()
        with pytest.raises(ServerBusyError) as busy:
            async with slot.hold("app list"):
                pass
        release.set()

    assert busy.value.holder == "backup create"
    # Released: the next call gets the slot.
    async with slot.hold("app list"):
        assert slot.holder == "app list"
    assert slot.holder is None
