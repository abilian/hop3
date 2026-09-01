# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""System status: resources, services, and host information.

`grid-size: 2` with `#info-panel { column-span: 2 }` — two half-width panels over one
full-width one. Here that is `vcat([hcat([a, b]), c])`.

Every panel shows either what the server reported or why it has nothing to show. It
used to show neither: CPU/memory/disk were the constants 42/63/81 on a timer, the
services panel rendered four services as RUNNING unconditionally, and the info panel
reported hostname `hop3.dev` running `v0.5.0` with 14 days of uptime.

The metrics stay unavailable until `Hop3Client.get_system_status` parses the server's
response (it currently makes the call and drops the result — see its docstring).
Saying so is the point: an empty panel that names its reason is recoverable, a
fabricated one is not.
"""

from __future__ import annotations

from collections.abc import Callable

from turbodesk import UI, Size, View, hcat, markup, vcat
from turbodesk.widgets import dialog

from hop3_tui.screens import Screen
from hop3_tui.screens._common import Action, bind, fill, halves
from hop3_tui.widgets import SystemStats, panel, status_panel
from hop3_tui.widgets.util import UNAVAILABLE

NAME_WIDTH = 12
#: Pressing `r` cannot refresh what is never fetched, and saying "refreshed" would be
#: the same defect one layer up.
NOTHING_TO_REFRESH = "System metrics are not reported by the server yet."


def services_panel(ui: UI, services: dict[str, bool] | None) -> View:
    """One line per service, green when it is up.

    `None` means nothing has been reported; `{}` means reported, and empty.
    """
    if services is None:
        return markup.render(ui.theme, UNAVAILABLE)
    if not services:
        return markup.render(ui.theme, "[dim]The server reported no services.[/]")
    lines = [
        f"{name:<{NAME_WIDTH}} " + ("[green]RUNNING[/]" if up else "[red]STOPPED[/]")
        for name, up in services.items()
    ]
    return markup.render_lines(ui.theme, "\n".join(lines))


def info_panel(ui: UI, hostname: str, version: str, uptime: str) -> View:
    return markup.render_lines(
        ui.theme,
        f"Hostname: {hostname or UNAVAILABLE}\n"
        f"Hop3:     {version or UNAVAILABLE}\n"
        f"Uptime:   {uptime or UNAVAILABLE}",
    )


def _ask_for_app(ui: UI, push: Callable[..., None]) -> None:
    """`ps` needs an app, and the system screen is not about one — so ask."""

    async def ask() -> None:
        name = await dialog.prompt(ui, "Processes", "Which application?")
        if name:
            push(Screen.PROCESSES, name)

    ui.spawn(ask())


def render(
    ui: UI,
    hop3,
    size: Size,
    *,
    argument: str = "",
    push: Callable[..., None] | None = None,
    switch: Callable[[Screen], None] | None = None,
) -> View:
    actions: dict[str, Action] = {}
    if push is not None:
        actions["l"] = lambda: push(Screen.SYSTEM_LOGS)
        actions["p"] = lambda: _ask_for_app(ui, push)
    actions["r"] = lambda: ui.notify(NOTHING_TO_REFRESH)
    bind(ui, actions)

    left, right = halves(size.width)
    top_height = max(5, size.height // 2)
    bottom_height = max(5, size.height - top_height)

    top = hcat([
        panel(
            ui,
            "Resources",
            status_panel(ui, SystemStats()),
            Size(left, top_height),
        ),
        panel(ui, "Services", services_panel(ui, None), Size(right, top_height)),
    ])
    bottom = panel(
        ui, "Info", info_panel(ui, "", "", ""), Size(size.width, bottom_height)
    )
    return fill(ui, vcat([top, bottom]), size)
