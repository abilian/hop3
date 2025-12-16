# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Status badge widget for displaying application state."""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static

from hop3_tui.api.models import AppState


class StatusBadge(Static):
    """A badge displaying application status with appropriate styling."""

    DEFAULT_CSS = """
    StatusBadge {
        width: auto;
        height: 1;
        padding: 0 1;
    }

    StatusBadge.running {
        background: $success;
        color: $text;
    }

    StatusBadge.stopped {
        background: $surface;
        color: $text-muted;
    }

    StatusBadge.failed {
        background: $error;
        color: $text;
    }

    StatusBadge.starting, StatusBadge.stopping {
        background: $warning;
        color: $text;
    }
    """

    state: reactive[AppState] = reactive(AppState.STOPPED)

    def __init__(self, state: AppState = AppState.STOPPED) -> None:
        super().__init__()
        self.state = state

    def watch_state(self, state: AppState) -> None:
        """Update display when state changes."""
        # Remove old state classes
        for old_state in AppState:
            self.remove_class(old_state.value.lower())

        # Add new state class
        self.add_class(state.value.lower())

        # Update text
        self.update(state.value)
