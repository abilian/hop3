# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Environment variables for one application.

`t` toggles whether secret values are shown — the one piece of screen-local state the
original kept as a reactive.
"""

from __future__ import annotations

from collections.abc import Callable

from turbodesk import UI, Size, View
from turbodesk.widgets import Column, dialog, table

from hop3_tui.api.client import Hop3ClientError
from hop3_tui.api.models import EnvVar
from hop3_tui.screens import Screen
from hop3_tui.screens._common import bind, fill, poll

# Declared: `ui.state(())` would type the slot as the empty tuple and then refuse
# the values put into it later.
NO_VARIABLES: tuple[EnvVar, ...] = ()

COLUMNS = [
    Column("name", weight=2),
    Column("value", weight=3),
    Column("type", width=10),
]
MASK = "****hidden****"
MAX_VALUE = 50
# Matched against the value, not the name: `API_URL=https://…` is not a secret, and
# `TOKEN` is only interesting because of what is stored in it.
SECRET_HINTS = ("sk-", "key", "secret", "password", "token", "auth", "credential")


KEYS = (
    ("a", "Add variable"),
    ("e", "Edit variable"),
    ("d", "Delete variable"),
    ("t", "Toggle secret values"),
    ("R", "Refresh"),
)


def is_secret(value: str) -> bool:
    lowered = value.lower()
    return any(hint in lowered for hint in SECRET_HINTS)


def format_value(value: str, *, reveal: bool) -> str:
    """What a cell shows: masked if secret and hidden, elided if long."""
    if not reveal and is_secret(value):
        return MASK
    if len(value) > MAX_VALUE:
        return value[: MAX_VALUE - 3] + "..."
    return value


def table_rows(variables: list, *, reveal: bool) -> list[list[str]]:
    rows = []
    for variable in variables:
        name = str(getattr(variable, "key", getattr(variable, "name", "")))
        value = str(getattr(variable, "value", ""))
        rows.append([
            name,
            format_value(value, reveal=reveal),
            "secret" if is_secret(value) else "plain",
        ])
    return rows


def render(
    ui: UI,
    hop3,
    size: Size,
    *,
    argument: str = "",
    push: Callable[..., None] | None = None,
    switch: Callable[[Screen], None] | None = None,
) -> View:
    name = argument or "(no app)"
    variables: tuple
    variables, set_variables = ui.state(NO_VARIABLES)
    selected: int
    selected, set_selected = ui.state(0)
    reveal: bool
    reveal, set_reveal = ui.state(False)

    async def refresh() -> None:
        try:
            fetched = await hop3.api_client.get_env_vars(name)
        except Hop3ClientError as error:
            ui.notify(f"Server error: {error}", kind="error", seconds=5)
        else:
            set_variables(tuple(fetched))

    poll(ui, 30.0, refresh)
    rows = list(variables)

    def chosen_key() -> str | None:
        if not (0 <= selected < len(rows)):
            return None
        return str(getattr(rows[selected], "key", getattr(rows[selected], "name", "")))

    def delete_var() -> None:
        key = chosen_key()
        if key is None:
            return

        async def ask() -> None:
            if not await dialog.confirm(
                ui, "Delete variable", f"Delete {key}?", yes="Delete"
            ):
                return
            try:
                await hop3.api_client.delete_env_var(name, key)
            except Hop3ClientError as error:
                ui.notify(f"Delete failed: {error}", kind="error", seconds=5)
            else:
                ui.notify(f"Deleted {key}")
                await refresh()

        ui.spawn(ask())

    async def store(key: str, value: str) -> None:
        try:
            await hop3.api_client.set_env_var(name, key, value)
        except Hop3ClientError as error:
            ui.notify(f"Could not set {key}: {error}", kind="error", seconds=5)
        else:
            ui.notify(f"Set {key}")
            await refresh()

    def add_var() -> None:
        async def ask() -> None:
            entered = await dialog.prompt(ui, "Add variable", "NAME=value")
            if not entered:
                return
            key, separator, value = entered.partition("=")
            if not separator or not key.strip():
                ui.notify("Expected NAME=value", kind="error")
                return
            await store(key.strip(), value)

        ui.spawn(ask())

    def edit_var() -> None:
        key = chosen_key()
        if key is None:
            return

        async def ask() -> None:
            entered = await dialog.prompt(ui, "Edit variable", f"New value for {key}?")
            if entered is not None:
                await store(key, entered)

        ui.spawn(ask())

    bind(
        ui,
        {
            "t": lambda: set_reveal(not reveal),
            "d": delete_var,
            "a": add_var,
            "e": edit_var,
            "R": lambda: ui.spawn(refresh()),
        },
    )

    return fill(
        ui,
        table(
            ui,
            COLUMNS,
            table_rows(rows, reveal=reveal),
            selected,
            size=size,
            on_move=set_selected,
            focus="env",
            empty="(no variables)",
        ),
        size,
    )
