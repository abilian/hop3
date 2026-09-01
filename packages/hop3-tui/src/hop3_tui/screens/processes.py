# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""How many workers of each type one application is scaled to."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from turbodesk import UI, Size, View, markup
from turbodesk.widgets import Column, table

from hop3_tui.api.client import Hop3ClientError
from hop3_tui.screens import Screen
from hop3_tui.screens._common import bind, fill, poll

# Declared: `ui.state(())` would type the slot as the empty tuple and then refuse
# the values put into it later.
NO_PROCESSES: tuple[dict[str, Any], ...] = ()

# `ps` answers "how many workers of each type is this app scaled to". The screen
# used to advertise pid, status, CPU, memory and uptime — five columns the server
# has no data for at all, on a table it only ever sends two.
COLUMNS = [
    Column("process type", weight=3),
    Column("count", width=8, align="right"),
]


KEYS = (("r", "Refresh"),)


def table_rows(processes: Sequence[dict[str, Any]]) -> list[list[str]]:
    return [
        [str(process.get("type", "")), str(process.get("count", 0))]
        for process in processes
    ]


def render(
    ui: UI,
    hop3,
    size: Size,
    *,
    argument: str = "",
    push: Callable[..., None],
    switch: Callable[[Screen], None],
) -> View:
    processes: tuple[dict[str, Any], ...]
    processes, set_processes = ui.state(NO_PROCESSES)
    selected: int
    selected, set_selected = ui.state(0)

    async def refresh() -> None:
        if not argument:
            return
        try:
            fetched = await hop3.api_client.get_processes(argument)
        except Hop3ClientError as error:
            ui.notify(f"Server error: {error}", kind="error", seconds=5)
        else:
            set_processes(tuple(fetched))

    poll(ui, 5.0, refresh)

    rows = list(processes)

    bind(ui, {"r": lambda: ui.spawn(refresh())})

    if not argument:
        # `ps` is app-scoped on the server; there is no server-wide process list.
        return fill(
            ui,
            markup.render(
                ui.theme, "[dim]No app selected. Open processes from an app.[/]"
            ),
            size,
        )

    return fill(
        ui,
        table(
            ui,
            COLUMNS,
            table_rows(rows),
            selected,
            size=size,
            on_move=set_selected,
            focus="processes",
            empty="(no processes)",
        ),
        size,
    )
