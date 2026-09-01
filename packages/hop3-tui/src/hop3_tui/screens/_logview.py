# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Shared log viewer, behind both the app logs and the system logs screens.

Both originals were the same screen twice: a scrolling pane, a filter box, a pause
toggle. One function with a fetch callback covers them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import NamedTuple

from turbodesk import UI, Size, Style, View, hcat, vcat
from turbodesk.widgets import less_keys, scroller, textbox

from hop3_tui.api.client import Hop3ClientError
from hop3_tui.screens._common import bind, fill, poll

Fetch = Callable[[], Awaitable[list[str]]]
# Declared: `ui.state(())` would type the slot as the empty tuple and then refuse
# the lines put into it later.
NO_LINES: tuple[str, ...] = ()

# The level marker the server puts in the line decides its colour.
LEVEL_ROLES = {"[ERROR]": "red", "[WARN]": "yellow", "[DEBUG]": "overlay1"}


class Status(NamedTuple):
    """What the heading says about the poll: a label, a detail, and a theme role."""

    label: str
    detail: str
    role: str


def status_line(*, paused: bool, problem: str, count: int) -> Status:
    """Unreachable beats paused beats live.

    A pane that goes on saying LIVE over a dead connection is the same lie as an
    invented log line, so the failure has to win over both other states.
    """
    if problem:
        return Status("UNREACHABLE", problem, "red")
    if paused:
        return Status("PAUSED", f"{count} lines", "peach")
    return Status("LIVE", f"{count} lines", "green")


def line_role(line: str) -> str:
    """Which theme role `line` is painted in, by the level it announces."""
    return next(
        (role for marker, role in LEVEL_ROLES.items() if marker in line), "subtext1"
    )


def log_view(ui: UI, size: Size, title: str, fetch: Fetch, interval: float) -> View:
    """A live log pane. Space pauses the poll; `/` focuses the filter."""
    lines, set_lines = ui.state(NO_LINES)
    paused: bool
    paused, set_paused = ui.state(False)
    #: Why the last poll failed, if it did. The heading has to stop saying LIVE:
    #: a stale pane over a dead connection is the same lie as an invented line.
    problem: str
    problem, set_problem = ui.state("")

    async def refresh() -> None:
        if paused:
            return
        try:
            fetched = await fetch()
        except Hop3ClientError as error:
            # Keep what we have — a blink of RPC failure must not blank a pane
            # someone is reading — but say that it is no longer live.
            set_problem(str(error))
        else:
            set_problem("")
            set_lines(tuple(fetched))

    poll(ui, interval, refresh)

    needle: str
    needle, set_needle = ui.state("")
    lowered = needle.lower()
    shown = (
        [line for line in lines if lowered in line.lower()] if needle else list(lines)
    )

    t = ui.theme
    status = status_line(paused=paused, problem=problem, count=len(shown))
    heading = View.text(
        f"  {title}  [{status.label}]  {status.detail}".ljust(size.width),
        Style(fg=t.crust, bg=t.role(status.role), bold=True),
    )
    dim = Style(fg=t.overlay1)
    if shown:
        body = vcat([
            View.text(line, Style(fg=t.role(line_role(line)))) for line in shown
        ])
    elif lines:
        body = View.text(f"No line matches {needle!r}.", dim)
    else:
        # The empty case is where a fabricated sample used to go.
        body = View.text("Nothing logged yet.", dim)
    # The pane owns the keyboard, not the filter: Space pauses and `/` moves to the
    # filter, so the filter must not have it already.
    ui.prefer_focus("log")
    pane = scroller(
        ui,
        body,
        Size(size.width, max(1, size.height - 2)),
        focus="log",
        stick_to_bottom=not paused,
    )
    filter_box = textbox(
        ui, focus="filter", initial=needle, width=max(10, size.width - 12)
    )
    if filter_box.value != needle:
        set_needle(filter_box.value)

    bind(
        ui,
        {
            " ": lambda: set_paused(not paused),
            "/": lambda: ui.set_focus("filter"),
            "g": lambda: pane.scroll_to(0),
            "G": lambda: pane.inject(less_keys.Action.BOTTOM),
            "d": lambda: ui.notify(f"{len(shown)} lines — download not wired up"),
        },
    )
    return fill(
        ui,
        vcat([
            heading,
            hcat([View.text(" Filter: "), filter_box.view]),
            pane.view,
        ]),
        size,
    )
