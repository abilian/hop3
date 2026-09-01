# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""A badge showing an application's state.

The original carried a `DEFAULT_CSS` block with one rule per state and swapped CSS
classes in a `watch_state` method. The mapping is the same; it just lives in a dict.
"""

from __future__ import annotations

from turbodesk import Style, Theme, View

from hop3_tui.api.models import AppState


def state_style(theme: Theme, state: AppState) -> Style:
    """The colours for `state` — the CSS classes of the original, as a lookup."""
    match state:
        case AppState.RUNNING:
            return Style(fg=theme.crust, bg=theme.green, bold=True)
        case AppState.FAILED | AppState.CRASHED:
            return Style(fg=theme.crust, bg=theme.red, bold=True)
        case AppState.STARTING | AppState.STOPPING:
            return Style(fg=theme.crust, bg=theme.yellow, bold=True)
        case _:
            return Style(fg=theme.subtext0, bg=theme.surface1)


def status_badge(theme: Theme, state: AppState) -> View:
    """`state` as a padded, coloured chip."""
    return View.text(f" {state.value} ", state_style(theme, state))
