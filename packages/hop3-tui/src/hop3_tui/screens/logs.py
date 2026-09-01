# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Logs for one application."""

from __future__ import annotations

from collections.abc import Callable

from turbodesk import UI, Size, View

from hop3_tui.screens import Screen
from hop3_tui.screens._logview import log_view

LOG_LINES = 200


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

    async def fetch() -> list[str]:
        return await hop3.api_client.get_app_logs(name, lines=LOG_LINES)

    return log_view(ui, size, f"Logs — {name}", fetch, 2.0)
