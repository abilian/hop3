# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Dashboard: server overview in four panels.

The original was `layout: grid; grid-size: 2` in CSS. Here `_grid` works the halves out
and `hcat`/`vcat` place them — eight lines, and the panels are the same four.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from turbodesk import UI, Size, View, hcat, markup, vcat

from hop3_tui.api.client import Hop3ClientError
from hop3_tui.api.models import AppState
from hop3_tui.screens import Screen
from hop3_tui.screens._common import bind, poll
from hop3_tui.widgets import SystemStats, panel, status_panel

NO_ACTIVITY = "[dim]No recent activity[/]"


KEYS = (
    ("r", "Refresh"),
    ("l", "System logs"),
)


class AppCounts(NamedTuple):
    """How many apps are in each state. Immutable — it lives in `ui.state`."""

    running: int = 0
    stopped: int = 0
    failed: int = 0

    @classmethod
    def of(cls, apps: list) -> AppCounts:
        return cls(
            running=sum(1 for app in apps if app.state == AppState.RUNNING),
            stopped=sum(1 for app in apps if app.state == AppState.STOPPED),
            failed=sum(1 for app in apps if app.state == AppState.FAILED),
        )


def apps_summary(ui: UI, counts: AppCounts) -> View:
    """The APPLICATIONS panel body."""
    return markup.render_lines(
        ui.theme,
        f"[green]Running:[/] {counts.running}\n"
        f"[dim]Stopped:[/] {counts.stopped}\n"
        f"[red]Failed:[/]  {counts.failed}",
    )


def render(
    ui: UI,
    hop3,
    size: Size,
    *,
    argument: str = "",
    push: Callable[..., None] | None = None,
    switch: Callable[[Screen], None] | None = None,
) -> View:
    """Four panels in a 2x2 grid, refreshed on the configured interval."""
    counts: AppCounts
    counts, set_counts = ui.state(AppCounts())

    async def refresh() -> None:
        try:
            apps = await hop3.api_client.list_apps()
        except Hop3ClientError as error:
            hop3.mark_api_failure()
            ui.notify(f"Server error: {error}", kind="error", seconds=5)
        else:
            hop3.mark_api_success()
            set_counts(AppCounts.of(apps))

    poll(ui, float(hop3.config.refresh_interval), refresh)

    def show_logs() -> None:
        if push is not None:
            push(Screen.SYSTEM_LOGS)

    def do_refresh() -> None:
        ui.spawn(refresh())
        ui.notify("Refreshing dashboard...")

    # Through `bind`, like every other screen: it is what the help panel is checked
    # against, so a bespoke handler here would be a key nothing could verify.
    bind(ui, {"r": do_refresh, "l": show_logs})

    cell = _cell_size(size)
    apps_panel = panel(ui, "Applications", apps_summary(ui, counts), cell)
    # Nothing fetches these yet: `Hop3Client.get_system_status` drops the response it
    # gets. The panel says so rather than showing the constants it used to.
    system = panel(ui, "System status", status_panel(ui, SystemStats()), cell)
    activity = panel(ui, "Recent activity", markup.render(ui.theme, NO_ACTIVITY), cell)
    # Built from KEYS, so the panel cannot advertise a key the screen does not bind.
    actions = panel(
        ui,
        "Actions",
        markup.render_lines(
            ui.theme,
            "\n".join(f"[bold]{key}[/]  {label}" for key, label in KEYS),
        ),
        cell,
    )

    if switch is not None:
        apps_panel = apps_panel.on_click(lambda: switch(Screen.APPS))
        system = system.on_click(lambda: switch(Screen.SYSTEM))

    return vcat([
        hcat([apps_panel, system]),
        hcat([activity, actions]),
    ])


def _cell_size(size: Size) -> Size:
    """One quarter of the screen. What `grid-size: 2` did, arithmetically."""
    return Size(max(10, size.width // 2), max(5, size.height // 2))
