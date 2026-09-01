# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""The screens, and the table the app dispatches through.

Textual's screens were `Screen` subclasses registered in `MODES` / `SCREENS` dicts and
instantiated on switch. Here a screen is a function with a fixed signature, and the
enum below is what the navigation state holds.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from turbodesk import UI, Size, View

    from hop3_tui.app import Hop3TUI


class Screen(Enum):
    """Every screen the app can show."""

    DASHBOARD = "dashboard"
    APPS = "apps"
    SYSTEM = "system"
    ADDONS = "addons"
    BACKUPS = "backups"
    CHAT = "chat"
    APP_DETAIL = "app_detail"
    LOGS = "logs"
    ENV_VARS = "env_vars"
    SYSTEM_LOGS = "system_logs"
    PROCESSES = "processes"


class Render(Protocol):
    """What every screen function looks like.

    `argument` is the one piece of context a pushed screen needs (an app name, so far).
    `push` and `switch` are how a screen navigates without knowing about the app.
    """

    def __call__(
        self,
        ui: UI,
        hop3: Hop3TUI,
        size: Size,
        *,
        argument: str,
        push: Callable[..., None],
        switch: Callable[[Screen], None],
    ) -> View: ...


def _registry() -> dict[Screen, Render]:
    """Imported inside a function: every screen imports `Screen` from this module."""
    from hop3_tui.screens import (
        addons,
        app_detail,
        apps,
        backups,
        chat,
        dashboard,
        env_vars,
        logs,
        processes,
        system,
        system_logs,
    )

    return {
        Screen.DASHBOARD: dashboard.render,
        Screen.APPS: apps.render,
        Screen.SYSTEM: system.render,
        Screen.ADDONS: addons.render,
        Screen.BACKUPS: backups.render,
        Screen.CHAT: chat.render,
        Screen.APP_DETAIL: app_detail.render,
        Screen.LOGS: logs.render,
        Screen.ENV_VARS: env_vars.render,
        Screen.SYSTEM_LOGS: system_logs.render,
        Screen.PROCESSES: processes.render,
    }


class _Screens:
    """Lazy dict, so importing the app does not import all eleven screens at once."""

    def __init__(self) -> None:
        self._table: dict[Screen, Render] | None = None

    def __getitem__(self, screen: Screen) -> Render:
        if self._table is None:
            self._table = _registry()
        return self._table[screen]


SCREENS = _Screens()

#: Screens whose keys live in a shared module rather than their own.
_SHARED_KEYS = {Screen.LOGS: "_logview", Screen.SYSTEM_LOGS: "_logview"}


def screen_keys(screen: Screen) -> tuple[tuple[str, str], ...]:
    """The (key, description) pairs a screen declares, for the help overlay.

    Imported on demand, like the render functions: `?` should not be the reason
    every screen module loads.
    """
    import importlib

    module = importlib.import_module(
        f"hop3_tui.screens.{_SHARED_KEYS.get(screen, screen.value)}"
    )
    return getattr(module, "KEYS", ())


__all__ = ["SCREENS", "Render", "Screen", "screen_keys"]
