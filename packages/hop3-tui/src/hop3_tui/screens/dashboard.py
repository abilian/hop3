# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Dashboard screen showing server overview."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from hop3_tui.api.models import AppState
from hop3_tui.widgets.status_panel import StatusPanel

if TYPE_CHECKING:
    from hop3_tui.app import Hop3TUI


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

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
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

    @property
    def hop3_app(self) -> Hop3TUI | None:
        """Get the Hop3TUI app instance if available."""
        if hasattr(self.app, "api_client"):
            return self.app  # type: ignore[return-value]
        return None

    def on_mount(self) -> None:
        """Initialize dashboard data."""
        refresh_interval = 5  # Default
        if self.hop3_app and self.hop3_app.config:
            refresh_interval = self.hop3_app.config.refresh_interval
        self.set_interval(refresh_interval, self._refresh_data)
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Refresh dashboard data from server."""
        self.run_worker(self._fetch_apps_data(), exclusive=True)

    async def _fetch_apps_data(self) -> None:
        """Fetch app data from server asynchronously."""
        if not self.hop3_app:
            # No API client available (e.g., in tests)
            return

        try:
            apps = await self.hop3_app.api_client.list_apps()

            # Count apps by state
            running = sum(1 for app in apps if app.state == AppState.RUNNING)
            stopped = sum(1 for app in apps if app.state == AppState.STOPPED)
            failed = sum(1 for app in apps if app.state == AppState.FAILED)

            # Update the summary widget
            apps_summary = self.query_one(AppsSummary)
            apps_summary.running = running
            apps_summary.stopped = stopped
            apps_summary.failed = failed

        except Exception as e:
            # On error, show notification but don't crash
            self.notify(f"Failed to fetch apps: {e}", severity="error", timeout=5)

    def action_refresh(self) -> None:
        """Manual refresh action."""
        self._refresh_data()
        self.notify("Refreshing dashboard...")
