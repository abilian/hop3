# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""The screens, and the table the app dispatches through.

Textual's screens were `Screen` subclasses registered in `MODES` / `SCREENS` dicts and
instantiated on switch. Here a screen is a function with a fixed signature, and the
enum below is what the navigation state holds.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from enum import Enum
from functools import cache
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


@cache
def _registry() -> dict[Screen, Render]:
    """Imported inside a function: every screen imports `Screen` from this module.

    Cached rather than assembled behind a hand-rolled lazy dict, so importing the
    app still does not drag in all eleven screens and there is no half-built state
    to guard against.
    """
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
    """`SCREENS[screen]`, without importing every screen to answer the first one."""

    def __getitem__(self, screen: Screen) -> Render:
        return _registry()[screen]


SCREENS = _Screens()


def screen_keys(screen: Screen) -> tuple[tuple[str, str], ...]:
    """The (key, description) pairs a screen declares, for the help overlay.

    The module is the one the render function came from, so a screen that borrows
    another's body (the two log views share `_logview`) borrows its keys too. A
    second table naming those modules was one rename away from disagreeing with
    this one.
    """
    module = sys.modules[_registry()[screen].__module__]
    return module.KEYS


__all__ = ["SCREENS", "Render", "Screen", "screen_keys"]
