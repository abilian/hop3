# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Applications: a filterable table with lifecycle actions.

The first screen to use `turbodesk.widgets.table`. The original's `ConfirmationDialog`
mounted as a widget with a `_pending_action` tuple to remember what it was confirming;
here `dialog.confirm` is awaited, so the answer and what to do with it stay together.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from turbodesk import UI, Size, View, hcat, vcat
from turbodesk.widgets import Cell, Column, dialog, table, textbox

from hop3_tui.api.client import Hop3ClientError
from hop3_tui.api.models import App
from hop3_tui.screens import Screen
from hop3_tui.screens._common import bind, fill, poll
from hop3_tui.widgets.status_badge import state_style

# What `app list` returns, and nothing more. `port`, `runtime` and `updated` were
# columns the server never fills: the first showed the instance count, the other two
# a dash on every row forever.
COLUMNS = [
    Column("name", weight=3),
    Column("status", width=9),
    Column("instances", width=10, align="right"),
]

MINUTE, HOUR, DAY = 60, 3600, 86400


def relative_time(moment: datetime | None) -> str:
    """ "3m ago" and friends. Lifted from the original unchanged in behaviour."""
    if moment is None:
        return "N/A"
    now = datetime.now(UTC)
    when = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment
    seconds = (now - when).total_seconds()
    if seconds < MINUTE:
        return "just now"
    if seconds < HOUR:
        return f"{int(seconds / MINUTE)}m ago"
    if seconds < DAY:
        return f"{int(seconds / HOUR)}h ago"
    return f"{int(seconds / DAY)}d ago"


def matching(apps: list[App], needle: str) -> list[App]:
    return (
        [app for app in apps if needle.lower() in app.name.lower()] if needle else apps
    )


def table_rows(ui: UI, apps: list[App]) -> list[list[Cell | str]]:
    return [
        [
            app.name,
            Cell(app.state.value, state_style(ui.theme, app.state)),
            str(app.workers),
        ]
        for app in apps
    ]


def render(
    ui: UI,
    hop3,
    size: Size,
    *,
    argument: str = "",
    push: Callable[..., None] | None = None,
    switch: Callable[[Screen], None] | None = None,
) -> View:
    apps: tuple[App, ...]
    apps, set_apps = ui.state(())
    selected: int
    selected, set_selected = ui.state(0)

    async def refresh() -> None:
        try:
            fetched = await hop3.api_client.list_apps()
        except Hop3ClientError as error:
            hop3.mark_api_failure()
            ui.notify(f"Server error: {error}", kind="error", seconds=5)
        else:
            hop3.mark_api_success()
            set_apps(tuple(fetched))

    poll(ui, float(hop3.config.refresh_interval) * 2, refresh)

    # The table owns the keyboard on arrival, not the filter box drawn above it —
    # otherwise every mode key would be typed into the filter. Without this, focus
    # would go to whichever registered first, which is source order.
    ui.prefer_focus("apps")
    needle: str
    needle, set_needle = ui.state("")
    shown = matching(list(apps), needle)

    def chosen() -> App | None:
        return shown[selected] if 0 <= selected < len(shown) else None

    async def act(verb: str, call, name: str) -> None:
        try:
            await call(name)
        except Hop3ClientError as error:
            ui.notify(f"Failed to {verb} {name}: {error}", kind="error", seconds=5)
        else:
            ui.notify(f"{verb.capitalize()}ed {name}")
            await refresh()

    def start() -> None:
        if (app := chosen()) is not None:
            ui.notify(f"Starting {app.name}...")
            ui.spawn(act("start", hop3.api_client.start_app, app.name))

    def restart() -> None:
        if (app := chosen()) is not None:
            ui.notify(f"Restarting {app.name}...")
            ui.spawn(act("restart", hop3.api_client.restart_app, app.name))

    def stop() -> None:
        app = chosen()
        if app is None:
            return

        async def ask() -> None:
            if await dialog.confirm(
                ui, "Stop application", f"Stop {app.name}?", yes="Stop"
            ):
                await act("stop", hop3.api_client.stop_app, app.name)

        ui.spawn(ask())

    def view() -> None:
        if push is not None and (app := chosen()) is not None:
            push(Screen.APP_DETAIL, app.name)

    def delete() -> None:
        app = chosen()
        if app is None:
            return

        async def ask() -> None:
            if await dialog.confirm(
                ui,
                "Delete application",
                f"Delete {app.name}? This cannot be undone.",
                yes="Delete",
            ):
                await act("delete", hop3.api_client.delete_app, app.name)

        ui.spawn(ask())

    def create() -> None:
        async def ask() -> None:
            name = await dialog.prompt(ui, "New application", "Name?")
            if not name:
                return
            # The server has no empty app: `app create` takes the repository to
            # create from, so the URL is required rather than an optional extra.
            repo_url = await dialog.prompt(
                ui, "New application", f"Git repository for {name}?"
            )
            if not repo_url:
                ui.notify("An application is created from a repository.", kind="warn")
                return
            try:
                await hop3.api_client.create_app(name, repo_url)
            except Hop3ClientError as error:
                ui.notify(f"Could not create {name}: {error}", kind="error", seconds=5)
                return
            ui.notify(f"Created {name}")

            if not await dialog.confirm(ui, "Deploy", f"Deploy {name} now?"):
                await refresh()
                return
            ui.notify(f"Deploying {name}...")
            try:
                await hop3.api_client.deploy_app(name)
            except Hop3ClientError as error:
                ui.notify(f"Deploy failed: {error}", kind="error", seconds=5)
            else:
                ui.notify(f"Deployed {name}")
            await refresh()

        ui.spawn(ask())

    bind(
        ui,
        {
            "s": start,
            "r": restart,
            "S": stop,
            "D": delete,
            "n": create,
            "R": lambda: ui.spawn(refresh()),
            "/": lambda: ui.set_focus("filter"),
        },
    )

    body_height = max(3, size.height - 2)
    listing = table(
        ui,
        COLUMNS,
        table_rows(ui, shown),
        selected,
        size=Size(size.width, body_height),
        on_move=set_selected,
        on_select=lambda _: view(),
        focus="apps",
        empty="(no apps)",
    )
    filter_box = textbox(
        ui, focus="filter", initial=needle, width=max(10, size.width - 12)
    )
    if filter_box.value != needle:
        set_needle(filter_box.value)

    return fill(
        ui,
        vcat([
            hcat([View.text(" Filter: "), filter_box.view]),
            listing,
        ]),
        size,
    )
