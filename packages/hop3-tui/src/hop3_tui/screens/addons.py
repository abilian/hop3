# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Add-ons: managed services attached to applications."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from turbodesk import UI, Size, View
from turbodesk.widgets import Column, dialog, table

from hop3_tui.api.client import Hop3ClientError
from hop3_tui.screens import Screen
from hop3_tui.screens._common import bind, fill, poll

# Declared: `ui.state(())` would type the slot as the empty tuple and then refuse
# the values put into it later.
NO_ADDONS: tuple[dict[str, Any], ...] = ()

# `addon list` returns [Name, Type, Attached apps]. There is no status column on
# the server; the one here read a fourth cell and showed "unknown" on every row.
COLUMNS = [
    Column("name", weight=2),
    Column("type", weight=2),
    Column("attached to", weight=3),
]

ADDON_TYPES = [
    ("postgresql", "PostgreSQL Database"),
    ("redis", "Redis Cache"),
    ("mysql", "MySQL Database"),
    ("mongodb", "MongoDB Database"),
]


KEYS = (
    ("n", "New add-on"),
    ("a", "Attach to an app"),
    ("d", "Detach from its app"),
    ("D", "Delete"),
    ("R", "Refresh"),
)


def table_rows(addons: Sequence[dict[str, Any]]) -> list[list[str]]:
    return [
        [
            str(addon.get("name", "")),
            str(addon.get("type", "")),
            str(addon.get("app_name") or "-"),
        ]
        for addon in addons
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
    addons: tuple[dict[str, Any], ...]
    addons, set_addons = ui.state(NO_ADDONS)
    selected: int
    selected, set_selected = ui.state(0)

    async def refresh() -> None:
        try:
            fetched = await hop3.api_client.list_addons()
        except Hop3ClientError as error:
            ui.notify(f"Server error: {error}", kind="error", seconds=5)
        else:
            set_addons(tuple(fetched))

    poll(ui, 15.0, refresh)
    rows = list(addons)

    def new_addon() -> None:
        async def ask() -> None:
            labels = [label for _, label in ADDON_TYPES]
            picked = await dialog.choose(ui, "New add-on", "Which kind?", labels)
            if picked is None:
                return
            kind = next(key for key, label in ADDON_TYPES if label == picked)
            name = await dialog.prompt(ui, "New add-on", f"Name for the {kind}?")
            if not name:
                return
            try:
                await hop3.api_client.create_addon(kind, name)
            except Hop3ClientError as error:
                ui.notify(f"Could not create: {error}", kind="error", seconds=5)
            else:
                ui.notify(f"Created {name}")
                await refresh()

        ui.spawn(ask())

    def chosen() -> dict[str, Any] | None:
        return rows[selected] if 0 <= selected < len(rows) else None

    def detach() -> None:
        """`d` — unhook the add-on from its app. Distinct from deleting it."""
        addon = chosen()
        if addon is None:
            ui.notify("No add-on selected", kind="warn")
            return
        app_name = str(addon.get("app_name") or "")
        if not app_name:
            ui.notify("Add-on is not attached to any app", kind="warn")
            return
        name = str(addon.get("name", ""))

        async def run() -> None:
            try:
                await hop3.api_client.detach_addon(name, app_name)
            except Hop3ClientError as error:
                ui.notify(f"Detach failed: {error}", kind="error", seconds=5)
            else:
                ui.notify(f"Detached {name} from {app_name}")
                await refresh()

        ui.spawn(run())

    def delete() -> None:
        """`D` — destroy it. The server refuses while it is still attached."""
        addon = chosen()
        if addon is None:
            ui.notify("No add-on selected", kind="warn")
            return
        name = str(addon.get("name", ""))
        if addon.get("app_name"):
            ui.notify("Cannot delete an attached add-on. Detach first.", kind="error")
            return

        async def ask() -> None:
            if not await dialog.confirm(
                ui, "Delete add-on", f"Delete {name}?", yes="Delete"
            ):
                return
            try:
                await hop3.api_client.delete_addon(name)
            except Hop3ClientError as error:
                ui.notify(f"Delete failed: {error}", kind="error", seconds=5)
            else:
                ui.notify(f"Deleted {name}")
                await refresh()

        ui.spawn(ask())

    def attach() -> None:
        addon = chosen()
        if addon is None:
            ui.notify("No add-on selected", kind="warn")
            return
        name = str(addon.get("name", ""))

        async def ask() -> None:
            app_name = await dialog.prompt(ui, "Attach add-on", f"Attach {name} to?")
            if not app_name:
                return
            try:
                await hop3.api_client.attach_addon(name, app_name)
            except Hop3ClientError as error:
                ui.notify(f"Attach failed: {error}", kind="error", seconds=5)
            else:
                ui.notify(f"Attached {name} to {app_name}")
                await refresh()

        ui.spawn(ask())

    bind(
        ui,
        {
            "n": new_addon,
            "a": attach,
            "d": detach,
            "D": delete,
            "R": lambda: ui.spawn(refresh()),
        },
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
            focus="addons",
            empty="(no add-ons)",
        ),
        size,
    )
