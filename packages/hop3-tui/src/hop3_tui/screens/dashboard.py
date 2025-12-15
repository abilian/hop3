# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Dashboard screen showing server overview."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from hop3_tui.widgets.status_panel import StatusPanel


class AppsSummary(Static):
    """Widget showing application summary counts."""

    running: reactive[int] = reactive(0)
    stopped: reactive[int] = reactive(0)
    failed: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Static("APPLICATIONS", classes="panel-title")
        yield Static(id="apps-summary-content")

    def on_mount(self) -> None:
        self._update_display()

    def watch_running(self, value: int) -> None:
        self._update_display()

    def watch_stopped(self, value: int) -> None:
        self._update_display()

    def watch_failed(self, value: int) -> None:
        self._update_display()

    def _update_display(self) -> None:
        content = self.query_one("#apps-summary-content", Static)
        content.update(
            f"[green]Running:[/green] {self.running}\n"
            f"[dim]Stopped:[/dim] {self.stopped}\n"
            f"[red]Failed:[/red]  {self.failed}"
        )

    def on_click(self) -> None:
        self.app.switch_mode("apps")


class QuickActions(Static):
    """Widget showing quick action buttons."""

    def compose(self) -> ComposeResult:
        yield Static("QUICK ACTIONS", classes="panel-title")
        yield Static(
            "[d] Deploy new app\n"
            "[b] Create backup\n"
            "[l] View system logs\n"
            "[c] Open chat",
            id="quick-actions-content",
        )


class RecentActivity(Static):
    """Widget showing recent activity."""

    def compose(self) -> ComposeResult:
        yield Static("RECENT ACTIVITY", classes="panel-title")
        yield Static(
            "[dim]No recent activity[/dim]",
            id="activity-content",
        )


class DashboardScreen(Screen):
    """Main dashboard screen."""

    CSS = """
    DashboardScreen {
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
        padding: 1;
    }

    .panel {
        border: solid $primary;
        padding: 1;
        height: 100%;
    }

    .panel-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #apps-panel {
        row-span: 1;
    }

    #apps-panel:hover {
        border: solid $accent;
    }

    #system-panel {
        row-span: 1;
    }

    #activity-panel {
        row-span: 1;
    }

    #actions-panel {
        row-span: 1;
    }
    """

    BINDINGS = [
        ("a", "switch_mode('apps')", "Apps"),
        ("s", "switch_mode('system')", "System"),
        ("c", "switch_mode('chat')", "Chat"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="apps-panel", classes="panel"):
            yield AppsSummary()
        with Container(id="system-panel", classes="panel"):
            yield StatusPanel()
        with Container(id="activity-panel", classes="panel"):
            yield RecentActivity()
        with Container(id="actions-panel", classes="panel"):
            yield QuickActions()
        yield Footer()

    def on_mount(self) -> None:
        """Initialize dashboard data."""
        self.set_interval(5, self._refresh_data)
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Refresh dashboard data from server."""
        # TODO: Fetch real data from API
        apps_summary = self.query_one(AppsSummary)
        apps_summary.running = 3
        apps_summary.stopped = 2
        apps_summary.failed = 0

    def action_refresh(self) -> None:
        """Manual refresh action."""
        self._refresh_data()
        self.notify("Dashboard refreshed")
