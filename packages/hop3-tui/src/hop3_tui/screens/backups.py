# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Backups: list, create, restore, delete."""

from __future__ import annotations

from collections.abc import Callable

from turbodesk import UI, Size, View
from turbodesk.widgets import Column, dialog, table

from hop3_tui.api.client import Hop3ClientError
from hop3_tui.api.models import Backup
from hop3_tui.screens import Screen
from hop3_tui.screens._common import bind, fill, poll

# Declared: `ui.state(())` would type the slot as the empty tuple and then refuse
# the values put into it later.
NO_BACKUPS: tuple[Backup, ...] = ()

COLUMNS = [
    Column("id", weight=2),
    Column("app", weight=2),
    Column("size", width=10, align="right"),
    Column("created", weight=2),
    Column("addons", weight=2),
]

KILOBYTE = 1024.0


KEYS = (
    ("n", "New backup"),
    ("d", "Delete"),
    ("r", "Restore"),
    ("R", "Refresh"),
)


def human_size(size: int | None) -> str:
    """Bytes as something a person reads. The original inlined this per row."""
    if not size:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < KILOBYTE:
            return f"{value:.0f}{unit}"
        value /= KILOBYTE
    return f"{value:.0f}TB"


def table_rows(backups: list) -> list[list[str]]:
    return [
        [
            str(getattr(backup, "id", "")),
            str(getattr(backup, "app_name", "")),
            human_size(getattr(backup, "size", None)),
            str(getattr(backup, "created_at", "") or "-"),
            ", ".join(getattr(backup, "addons", []) or []) or "-",
        ]
        for backup in backups
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
    backups: tuple
    backups, set_backups = ui.state(NO_BACKUPS)
    selected: int
    selected, set_selected = ui.state(0)

    async def refresh() -> None:
        try:
            fetched = await hop3.api_client.list_backups()
        except Hop3ClientError as error:
            ui.notify(f"Server error: {error}", kind="error", seconds=5)
        else:
            set_backups(tuple(fetched))

    poll(ui, 15.0, refresh)
    rows = list(backups)

    def chosen_id() -> str | None:
        return str(rows[selected].id) if 0 <= selected < len(rows) else None

    def new_backup() -> None:
        async def ask() -> None:
            name = await dialog.prompt(ui, "New backup", "Which application?")
            if not name:
                return
            try:
                await hop3.api_client.create_backup(name)
            except Hop3ClientError as error:
                ui.notify(f"Backup failed: {error}", kind="error", seconds=5)
            else:
                ui.notify(f"Backup of {name} started")
                await refresh()

        ui.spawn(ask())

    def delete_backup() -> None:
        backup_id = chosen_id()
        if backup_id is None:
            return

        async def ask() -> None:
            if not await dialog.confirm(
                ui, "Delete backup", f"Delete {backup_id}?", yes="Delete"
            ):
                return
            try:
                await hop3.api_client.delete_backup(backup_id)
            except Hop3ClientError as error:
                ui.notify(f"Delete failed: {error}", kind="error", seconds=5)
            else:
                ui.notify(f"Deleted {backup_id}")
                await refresh()

        ui.spawn(ask())

    def restore() -> None:
        backup_id = chosen_id()
        if backup_id is None:
            return

        async def ask() -> None:
            if not await dialog.confirm(
                ui,
                "Restore backup",
                f"Restore {backup_id}? This overwrites current data.",
                yes="Restore",
            ):
                return
            try:
                await hop3.api_client.restore_backup(backup_id)
            except Hop3ClientError as error:
                ui.notify(f"Restore failed: {error}", kind="error", seconds=5)
            else:
                ui.notify(f"Restored {backup_id}")
                await refresh()

        ui.spawn(ask())

    bind(
        ui,
        {
            "n": new_backup,
            "d": delete_backup,
            "r": restore,
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
            focus="backups",
            empty="(no backups)",
        ),
        size,
    )
