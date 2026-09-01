# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""One application: its details, its actions, a peek at its logs."""

from __future__ import annotations

from collections.abc import Callable

from turbodesk import UI, Size, Style, View, hcat, markup, vcat
from turbodesk.widgets import dialog

from hop3_tui.api.client import Hop3ClientError
from hop3_tui.api.models import App
from hop3_tui.screens import Screen
from hop3_tui.screens._common import Bindings, bind, fill, halves, poll
from hop3_tui.widgets import panel
from hop3_tui.widgets.status_badge import status_badge

# Declared: `ui.state(())` would type the slot as the empty tuple and then refuse
# the values put into it later.
NO_LOGS: tuple[str, ...] = ()

ACTIONS = (
    "[l] View logs",
    "[e] Environment variables",
    "[s] Stop",
    "[r] Restart",
)
PREVIEW_LINES = 8


KEYS = (
    ("s", "Stop"),
    ("r", "Restart"),
    ("l", "Logs"),
    ("e", "Environment"),
    ("R", "Refresh"),
)


def info_panel(ui: UI, app: App | None) -> View:
    """What `app status` reports, and nothing it doesn't.

    `Runtime` used to sit at the top of this panel reading the model's `"unknown"`
    default: the server has no runtime field, so the line said the same word about
    every application forever.
    """
    if app is None:
        return markup.render(ui.theme, "[dim]loading…[/]")
    lines = [f"Name:     {app.name}", f"Port:     {app.port or '-'}"]
    if app.hostname:
        lines.append(f"URL:      https://{app.hostname}")
    if app.error_message:
        lines.append(f"[red]Error:[/]    {app.error_message}")
    return vcat([
        hcat([View.text("State:    "), status_badge(ui.theme, app.state)]),
        markup.render_lines(ui.theme, "\n".join(lines)),
    ])


def render(
    ui: UI,
    hop3,
    size: Size,
    *,
    argument: str = "",
    push: Callable[..., None],
    switch: Callable[[Screen], None],
) -> View:
    name = argument or "(no app)"
    app: App | None
    app, set_app = ui.state(None)
    logs: tuple[str, ...]
    logs, set_logs = ui.state(NO_LOGS)

    async def refresh() -> None:
        try:
            fetched = await hop3.api_client.get_app(name)
            tail = await hop3.api_client.get_app_logs(name, lines=PREVIEW_LINES)
        except Hop3ClientError as error:
            ui.notify(f"Server error: {error}", kind="error", seconds=5)
        else:
            set_app(fetched)
            set_logs(tuple(tail))

    poll(ui, float(hop3.config.refresh_interval), refresh)

    async def act(verb: str, call) -> None:
        try:
            await call(name)
        except Hop3ClientError as error:
            ui.notify(f"Failed to {verb} {name}: {error}", kind="error", seconds=5)
        else:
            ui.notify(f"{verb.capitalize()}ed {name}")
            await refresh()

    def stop() -> None:
        async def ask() -> None:
            if await dialog.confirm(
                ui, "Stop application", f"Stop {name}?", yes="Stop"
            ):
                await act("stop", hop3.api_client.stop_app)

        ui.spawn(ask())

    actions: Bindings = {
        "s": stop,
        "r": lambda: ui.spawn(act("restart", hop3.api_client.restart_app)),
        "R": lambda: ui.spawn(refresh()),
    }
    actions["l"] = lambda: push(Screen.LOGS, name)
    actions["e"] = lambda: push(Screen.ENV_VARS, name)
    bind(ui, actions)

    left, right = halves(size.width)
    top_height = max(6, size.height // 2)
    bottom_height = max(4, size.height - top_height)

    preview = vcat([
        View.text(line, Style(fg=ui.theme.subtext1)) for line in logs
    ]) or markup.render(ui.theme, "[dim]no output yet[/]")

    return fill(
        ui,
        vcat([
            hcat([
                panel(ui, name, info_panel(ui, app), Size(left, top_height)),
                panel(
                    ui,
                    "Actions",
                    markup.render_lines(ui.theme, "\n".join(ACTIONS)),
                    Size(right, top_height),
                ),
            ]),
            panel(ui, "Recent logs", preview, Size(size.width, bottom_height)),
        ]),
        size,
    )
