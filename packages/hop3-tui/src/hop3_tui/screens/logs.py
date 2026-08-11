# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Logs viewing screen, polling the server for an app's log lines."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from hop3_tui.app import Hop3TUI

#: The client offers no incremental log call, so the whole tail is re-fetched.
#: Matched to SystemLogsScreen rather than chosen: one interval to reason about.
POLL_SECONDS = 2
LOG_LINES = 100


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

    BINDINGS: ClassVar = [
        Binding("escape", "go_back", "Back"),
        Binding("space", "toggle_pause", "Pause/Resume"),
        Binding("/", "focus_filter", "Filter"),
        Binding("g", "scroll_top", "Top"),
        Binding("G", "scroll_bottom", "Bottom"),
        Binding("d", "download_logs", "Download"),
    ]

    paused: reactive[bool] = reactive(False)
    auto_scroll: reactive[bool] = reactive(True)

    def __init__(self, app_name: str = "") -> None:
        super().__init__()
        self.app_name = app_name
        self._logs: list[str] = []
        self._filter_text = ""
        #: Why the pane is empty, when it is. Empty string means "it isn't".
        self._empty_reason = ""

    @property
    def hop3_app(self) -> Hop3TUI | None:
        """Get the Hop3TUI app instance if available."""
        if hasattr(self.app, "api_client"):
            return cast("Hop3TUI", self.app)
        return None

    def compose(self) -> ComposeResult:
        yield Header()
        with Static(id="logs-header"):
            yield Static(f"Logs: {self.app_name}", id="logs-title")
            yield Static("[green]POLLING[/]", id="logs-status")
        with VerticalScroll(id="logs-container"):
            yield Static(id="logs-content")
        with Static(id="filter-bar"):
            yield Input(placeholder="Filter logs...", id="filter-input")
        yield Footer()

    def on_mount(self) -> None:
        """Start loading logs."""
        self._poll_new_logs()
        self.set_interval(POLL_SECONDS, self._poll_new_logs)

    def _poll_new_logs(self) -> None:
        """Re-fetch the log tail from the server."""
        if self.paused:
            return
        self.run_worker(self._fetch_logs(), exclusive=True)

    async def _fetch_logs(self) -> None:
        """
        Replace the displayed lines with what the server currently holds.

        Every failure mode puts its reason on screen. This pane used to render
        a hardcoded eight-line sample and append an invented line roughly every
        three seconds, so it showed a plausible `[ERROR] Failed to connect to
        redis` for an app that was fine — and ``action_download_logs`` would
        write those invented lines to a file the operator could attach to a bug
        report.
        """
        if not self.app_name:
            self._show_nothing("No app selected. Open logs from an app's detail view.")
            return

        hop3_app = self.hop3_app
        if hop3_app is None:
            self._show_nothing("Not connected to a server, so there are no logs.")
            return

        try:
            lines = await hop3_app.api_client.get_app_logs(
                self.app_name, lines=LOG_LINES
            )
        except Exception as e:  # ken: the client raises broadly; siblings match
            # Keep whatever we last got: a transient RPC failure should not
            # blank a screen the operator may be reading.
            self.notify(f"Failed to fetch logs: {e}", severity="error")
            self._empty_reason = f"Could not reach the server: {e}"
            self._update_display()
            return

        self._logs = [line for line in lines if line.strip()]
        self._empty_reason = (
            "" if self._logs else f"{self.app_name} has not logged anything yet."
        )
        self._update_display()

    def _show_nothing(self, reason: str) -> None:
        """Clear the pane and say why it is empty."""
        self._logs = []
        self._empty_reason = reason
        self._update_display()

    def _update_display(self) -> None:
        """Update the logs display."""
        content = self.query_one("#logs-content", Static)
        filtered_logs = self._get_filtered_logs()

        if filtered_logs:
            styled_lines = [self._style_log_line(line) for line in filtered_logs]
            content.update("\n".join(styled_lines))
        elif self._logs:
            content.update(f"[dim]No line matches {self._filter_text!r}.[/]")
        else:
            content.update(f"[dim]{self._empty_reason}[/]")

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

    def watch_paused(self, paused: bool) -> None:
        """Update status when paused state changes."""
        status = self.query_one("#logs-status", Static)
        if paused:
            status.update("[yellow]PAUSED[/]")
        else:
            status.update("[green]POLLING[/]")

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
