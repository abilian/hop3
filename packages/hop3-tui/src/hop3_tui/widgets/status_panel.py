# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Status panel widget for system resource display."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static


class StatusPanel(Static):
    """Panel showing system status with progress bars."""

    cpu: reactive[float] = reactive(0.0)
    memory: reactive[float] = reactive(0.0)
    disk: reactive[float] = reactive(0.0)
    uptime: reactive[str] = reactive("0s")

    def compose(self) -> ComposeResult:
        yield Static("SYSTEM STATUS", classes="panel-title")
        yield Static(id="status-content")

    def on_mount(self) -> None:
        self._update_display()
        # Start auto-refresh
        self.set_interval(5, self._refresh_stats)

    def _refresh_stats(self) -> None:
        """Refresh stats from server."""
        # TODO: Fetch from API
        self.cpu = 42.0
        self.memory = 63.0
        self.disk = 81.0
        self.uptime = "14d 3h 22m"

    def watch_cpu(self, value: float) -> None:
        self._update_display()

    def watch_memory(self, value: float) -> None:
        self._update_display()

    def watch_disk(self, value: float) -> None:
        self._update_display()

    def watch_uptime(self, value: str) -> None:
        self._update_display()

    def _update_display(self) -> None:
        content = self.query_one("#status-content", Static)
        content.update(
            f"CPU:    {self._make_bar(self.cpu)} {self.cpu:.0f}%\n"
            f"Memory: {self._make_bar(self.memory)} {self.memory:.0f}%\n"
            f"Disk:   {self._make_bar(self.disk)} {self.disk:.0f}%\n"
            f"Uptime: {self.uptime}"
        )

    def _make_bar(self, percent: float, width: int = 10) -> str:
        """Create a progress bar string."""
        filled = int(percent / 100 * width)
        empty = width - filled

        # Color based on percentage
        if percent >= 90:
            color = "red"
        elif percent >= 70:
            color = "yellow"
        else:
            color = "green"

        return f"[{color}]{'█' * filled}[/][dim]{'░' * empty}[/]"

    def on_click(self) -> None:
        """Navigate to system screen on click."""
        self.app.switch_mode("system")
