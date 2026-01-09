# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Logs viewing screen with streaming support."""

from __future__ import annotations

import random
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static


class LogsScreen(Screen):
    """Screen for viewing application logs."""

    CSS = """
    LogsScreen {
        layout: vertical;
    }

    #logs-header {
        height: 3;
        padding: 0 1;
        background: $primary-darken-2;
    }

    #logs-title {
        text-style: bold;
    }

    #logs-status {
        dock: right;
    }

    #logs-container {
        height: 1fr;
        padding: 0 1;
    }

    #logs-content {
        height: auto;
    }

    .log-line {
        height: auto;
    }

    .log-info {
        color: $text;
    }

    .log-warn {
        color: $warning;
    }

    .log-error {
        color: $error;
    }

    .log-debug {
        color: $text-muted;
    }

    #filter-bar {
        dock: bottom;
        height: 3;
        padding: 0 1;
        background: $surface;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back"),
        Binding("space", "toggle_pause", "Pause/Resume"),
        Binding("/", "focus_filter", "Filter"),
        Binding("g", "scroll_top", "Top"),
        Binding("G", "scroll_bottom", "Bottom"),
        Binding("d", "download_logs", "Download"),
    ]

    paused: reactive[bool] = reactive(False)  # noqa: FBT003
    auto_scroll: reactive[bool] = reactive(True)  # noqa: FBT003

    def __init__(self, app_name: str = "") -> None:
        super().__init__()
        self.app_name = app_name
        self._logs: list[str] = []
        self._filter_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Static(id="logs-header"):
            yield Static(f"Logs: {self.app_name}", id="logs-title")
            yield Static("[green]STREAMING[/]", id="logs-status")
        with VerticalScroll(id="logs-container"):
            yield Static(id="logs-content")
        with Static(id="filter-bar"):
            yield Input(placeholder="Filter logs...", id="filter-input")
        yield Footer()

    def on_mount(self) -> None:
        """Start loading logs."""
        self._load_initial_logs()
        # Start streaming (simulated with interval for now)
        self.set_interval(1, self._poll_new_logs)

    def _load_initial_logs(self) -> None:
        """Load initial log lines."""
        # TODO: Fetch from API
        self._logs = [
            "10:32:15.123 [INFO]  Request processed in 45ms",
            "10:32:14.987 [INFO]  GET /api/users 200",
            "10:32:14.542 [DEBUG] Cache hit for user:123",
            "10:32:10.234 [INFO]  Database query completed",
            "10:32:09.876 [WARN]  Slow query detected (>100ms)",
            "10:32:05.432 [INFO]  New connection from 10.0.0.5",
            "10:32:01.111 [ERROR] Failed to connect to redis",
            "10:31:55.000 [INFO]  Server started on port 8000",
        ]
        self._update_display()

    def _poll_new_logs(self) -> None:
        """Poll for new log lines (simulate streaming)."""
        if self.paused:
            return

        # TODO: Fetch new logs from API
        # For demo, occasionally add a new line
        if random.random() > 0.7:
            levels = ["INFO", "DEBUG", "WARN"]
            level = random.choice(levels)
            self._logs.append(f"10:32:20.000 [{level}]  New log entry")
            self._update_display()

    def _update_display(self) -> None:
        """Update the logs display."""
        content = self.query_one("#logs-content", Static)
        filtered_logs = self._get_filtered_logs()

        styled_lines = []
        for line in filtered_logs:
            styled_lines.append(self._style_log_line(line))

        content.update("\n".join(styled_lines))

        # Auto-scroll to bottom if enabled
        if self.auto_scroll and not self.paused:
            container = self.query_one("#logs-container", VerticalScroll)
            container.scroll_end(animate=False)

    def _get_filtered_logs(self) -> list[str]:
        """Get logs filtered by current filter text."""
        if not self._filter_text:
            return self._logs
        return [log for log in self._logs if self._filter_text.lower() in log.lower()]

    def _style_log_line(self, line: str) -> str:
        """Apply styling to a log line based on level."""
        if "[ERROR]" in line:
            return f"[red]{line}[/]"
        if "[WARN]" in line:
            return f"[yellow]{line}[/]"
        if "[DEBUG]" in line:
            return f"[dim]{line}[/]"
        return line

    def watch_paused(self, paused: bool) -> None:  # noqa: FBT001
        """Update status when paused state changes."""
        status = self.query_one("#logs-status", Static)
        if paused:
            status.update("[yellow]PAUSED[/]")
        else:
            status.update("[green]STREAMING[/]")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes."""
        if event.input.id == "filter-input":
            self._filter_text = event.value
            self._update_display()

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.app.pop_screen()

    def action_toggle_pause(self) -> None:
        """Toggle pause/resume streaming."""
        self.paused = not self.paused

    def action_focus_filter(self) -> None:
        """Focus the filter input."""
        self.query_one("#filter-input", Input).focus()

    def action_scroll_top(self) -> None:
        """Scroll to top of logs."""
        self.auto_scroll = False
        container = self.query_one("#logs-container", VerticalScroll)
        container.scroll_home()

    def action_scroll_bottom(self) -> None:
        """Scroll to bottom of logs."""
        self.auto_scroll = True
        container = self.query_one("#logs-container", VerticalScroll)
        container.scroll_end()

    def action_download_logs(self) -> None:
        """Download logs to file."""
        if not self._logs:
            self.notify("No logs to download", severity="warning")
            return

        # Create filename with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{self.app_name or 'logs'}_{timestamp}.log"

        # Write to downloads directory or current directory
        downloads = Path.home() / "Downloads"
        if downloads.exists():
            filepath = downloads / filename
        else:
            filepath = Path.cwd() / filename

        try:
            with filepath.open("w") as f:
                f.write("\n".join(self._logs))
            self.notify(f"[green]Logs saved to {filepath}[/]", timeout=5)
        except OSError as e:
            self.notify(f"Failed to save logs: {e}", severity="error")
