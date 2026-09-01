# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""System-wide logs."""

from __future__ import annotations

from collections.abc import Callable

from turbodesk import UI, Size, View

from hop3_tui.screens import Screen
from hop3_tui.screens._logview import KEYS, log_view

#: Re-exported so `screen_keys` finds this screen's keys where its render
#: function lives. Both log screens are `_logview`, keys included.
__all__ = ["KEYS", "render"]

LOG_LINES = 200


def render(
    ui: UI,
    hop3,
    size: Size,
    *,
    argument: str = "",
    push: Callable[..., None],
    switch: Callable[[Screen], None],
) -> View:
    async def fetch() -> list[str]:
        return await hop3.api_client.get_system_logs(lines=LOG_LINES)

    return log_view(ui, size, "System logs", fetch, 3.0)
