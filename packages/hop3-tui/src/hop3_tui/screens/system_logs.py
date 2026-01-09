# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""System logs viewing screen."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static

if TYPE_CHECKING:
    from hop3_tui.app import Hop3TUI


class SystemLogsScreen(Screen):
    """Screen for viewing system logs."""

    CSS = """
    SystemLogsScreen {
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

    #status-bar {
        dock: top;
        height: 1;
        padding: 0 1;
        background: $surface;
    }

    #logs-container {
        height: 1fr;
        padding: 0 1;
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

    def __init__(self) -> None:
        super().__init__()
        self._logs: list[str] = []
        self._filter_text: str = ""

    @property
    def hop3_app(self) -> Hop3TUI | None:
        """Get the Hop3TUI app instance if available."""
        if hasattr(self.app, "api_client"):
            return self.app  # type: ignore[return-value]
        return None

    def compose(self) -> ComposeResult:
        yield Header()
        with Static(id="logs-header"):
            yield Static("System Logs", id="logs-title")
        yield Static("[green]STREAMING[/]", id="status-bar")
        with VerticalScroll(id="logs-container"):
            yield Static(id="logs-content")
        with Static(id="filter-bar"):
            yield Input(placeholder="Filter logs...", id="filter-input")
        yield Footer()

    def on_mount(self) -> None:
        """Start log streaming."""
        self._load_initial_logs()
        self.set_interval(2, self._fetch_new_logs)

    def _load_initial_logs(self) -> None:
        """Load initial logs."""
        self.run_worker(self._fetch_logs())

    async def _fetch_logs(self) -> None:
        """Fetch logs from server."""
        if not self.hop3_app:
            # Mock data for testing
            self._logs = [
                "2024-03-15 10:32:15 [INFO] System started",
                "2024-03-15 10:32:16 [INFO] Loading configuration",
                "2024-03-15 10:32:17 [INFO] nginx: started",
                "2024-03-15 10:32:18 [INFO] supervisor: started",
                "2024-03-15 10:32:19 [INFO] postgresql: started",
                "2024-03-15 10:32:20 [INFO] redis: started",
                "2024-03-15 10:33:00 [INFO] All services running",
                "2024-03-15 10:35:00 [WARN] High memory usage detected: 85%",
                "2024-03-15 10:40:00 [INFO] Scheduled backup started",
                "2024-03-15 10:42:00 [INFO] Backup completed successfully",
                "2024-03-15 11:00:00 [DEBUG] Health check: all services OK",
                "2024-03-15 11:15:00 [ERROR] Connection timeout to external API",
                "2024-03-15 11:15:05 [INFO] Retrying connection...",
                "2024-03-15 11:15:10 [INFO] Connection restored",
            ]
            self._update_display()
            return

        try:
            self._logs = await self.hop3_app.api_client.get_system_logs(lines=100)
            self._update_display()
        except Exception as e:
            self.notify(f"Failed to fetch logs: {e}", severity="error")

    def _fetch_new_logs(self) -> None:
        """Fetch new logs periodically."""
        if self.paused:
            return
        # In a real implementation, this would fetch only new logs
        # For now, we'll just add a simulated new log line
        if not self.hop3_app and self._logs:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            self._logs.append(f"{now} [INFO] Health check: OK")
            self._update_display()

    def _update_display(self) -> None:
        """Update the logs display."""
        content = self.query_one("#logs-content", Static)

        # Filter logs if filter text is set
        if self._filter_text:
            filtered = [
                log for log in self._logs if self._filter_text.lower() in log.lower()
            ]
        else:
            filtered = self._logs

        # Style each line based on log level
        styled_lines = [self._style_log_line(line) for line in filtered]
        content.update("\n".join(styled_lines))

        # Auto-scroll to bottom
        if self.auto_scroll:
            container = self.query_one("#logs-container", VerticalScroll)
            container.scroll_end(animate=False)

    def _style_log_line(self, line: str) -> str:
        """Apply styling based on log level."""
        line_lower = line.lower()
        if "[error]" in line_lower or "error" in line_lower:
            return f"[red]{line}[/]"
        if "[warn]" in line_lower or "warning" in line_lower:
            return f"[yellow]{line}[/]"
        if "[debug]" in line_lower:
            return f"[dim]{line}[/]"
        return line

    def watch_paused(self, paused: bool) -> None:  # noqa: FBT001
        """Update status bar when paused state changes."""
        status = self.query_one("#status-bar", Static)
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

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"system_logs_{timestamp}.log"

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
