# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Applications list screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static

from hop3_tui.api.models import App, AppState

if TYPE_CHECKING:
    from hop3_tui.app import Hop3TUI


class AppsScreen(Screen):
    """Screen showing list of all applications."""

    CSS = """
    AppsScreen {
        layout: vertical;
    }

    #filter-bar {
        dock: top;
        height: 3;
        padding: 0 1;
    }

    #filter-input {
        width: 100%;
    }

    #apps-table {
        height: 1fr;
    }

    .status-running {
        color: $success;
    }

    .status-stopped {
        color: $text-muted;
    }

    .status-failed {
        color: $error;
    }

    .status-transitional {
        color: $warning;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "switch_mode('dashboard')", "Back"),
        Binding("enter", "view_app", "View"),
        Binding("s", "start_app", "Start"),
        Binding("S", "stop_app", "Stop"),
        Binding("r", "restart_app", "Restart"),
        Binding("n", "new_app", "New"),
        Binding("/", "focus_filter", "Filter"),
        Binding("R", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._apps: list[App] = []
        self._filter_text: str = ""

    @property
    def hop3_app(self) -> Hop3TUI | None:
        """Get the Hop3TUI app instance if available."""
        if hasattr(self.app, "api_client"):
            return self.app  # type: ignore[return-value]
        return None

    def compose(self) -> ComposeResult:
        yield Header()
        with Static(id="filter-bar"):
            yield Input(placeholder="Filter apps...", id="filter-input")
        yield DataTable(id="apps-table")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the apps table."""
        table = self.query_one("#apps-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("NAME", "STATUS", "PORT", "RUNTIME", "UPDATED")

        # Load initial data
        self._refresh_apps()
        refresh_interval = 10  # Default
        if self.hop3_app and self.hop3_app.config:
            refresh_interval = self.hop3_app.config.refresh_interval * 2
        self.set_interval(refresh_interval, self._refresh_apps)

    def _refresh_apps(self) -> None:
        """Refresh apps list from server."""
        self.run_worker(self._fetch_apps(), exclusive=True)

    async def _fetch_apps(self) -> None:
        """Fetch apps from server asynchronously."""
        if not self.hop3_app:
            # No API client available (e.g., in tests)
            return

        try:
            self._apps = await self.hop3_app.api_client.list_apps()
            self._update_table()
        except Exception as e:
            self.notify(f"Failed to fetch apps: {e}", severity="error", timeout=5)

    def _update_table(self) -> None:
        """Update the table with current apps."""
        table = self.query_one("#apps-table", DataTable)
        table.clear()

        for app in self._apps:
            if self._filter_text and self._filter_text.lower() not in app.name.lower():
                continue

            status_style = self._get_status_style(app.state)
            port_str = str(app.port) if app.port else "-"
            updated = self._format_updated(app)

            table.add_row(
                app.name,
                f"[{status_style}]{app.state.value}[/]",
                port_str,
                app.runtime,
                updated,
                key=app.name,
            )

    def _format_updated(self, app: App) -> str:
        """Format the updated timestamp."""
        if app.updated_at:
            # Simple relative time
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            if app.updated_at.tzinfo is None:
                # Assume UTC if no timezone
                delta = now - app.updated_at.replace(tzinfo=timezone.utc)
            else:
                delta = now - app.updated_at

            seconds = delta.total_seconds()
            if seconds < 60:
                return "just now"
            if seconds < 3600:
                mins = int(seconds / 60)
                return f"{mins}m ago"
            if seconds < 86400:
                hours = int(seconds / 3600)
                return f"{hours}h ago"
            days = int(seconds / 86400)
            return f"{days}d ago"
        return "N/A"

    def _get_status_style(self, state: AppState) -> str:
        """Get the style for a status."""
        match state:
            case AppState.RUNNING:
                return "green"
            case AppState.STOPPED:
                return "dim"
            case AppState.FAILED:
                return "red"
            case AppState.STARTING | AppState.STOPPING:
                return "yellow"
            case _:
                return "white"

    def _get_selected_app_name(self) -> str | None:
        """Get the name of the currently selected app."""
        table = self.query_one("#apps-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            return str(table.get_cell_at((table.cursor_row, 0)))
        return None

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes."""
        if event.input.id == "filter-input":
            self._filter_text = event.value
            self._update_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (Enter key)."""
        self.action_view_app()

    def action_focus_filter(self) -> None:
        """Focus the filter input."""
        self.query_one("#filter-input", Input).focus()

    def action_view_app(self) -> None:
        """View the selected application."""
        app_name = self._get_selected_app_name()
        if app_name:
            self.hop3_app.push_app_detail(app_name)

    def action_start_app(self) -> None:
        """Start the selected application."""
        app_name = self._get_selected_app_name()
        if app_name:
            self.notify(f"Starting {app_name}...")
            self.run_worker(self._start_app(app_name))

    async def _start_app(self, app_name: str) -> None:
        """Start an app asynchronously."""
        try:
            await self.hop3_app.api_client.start_app(app_name)
            self.notify(f"[green]Started {app_name}[/]")
            self._refresh_apps()
        except Exception as e:
            self.notify(f"Failed to start {app_name}: {e}", severity="error")

    def action_stop_app(self) -> None:
        """Stop the selected application."""
        app_name = self._get_selected_app_name()
        if app_name:
            # TODO: Add confirmation dialog
            self.notify(f"Stopping {app_name}...")
            self.run_worker(self._stop_app(app_name))

    async def _stop_app(self, app_name: str) -> None:
        """Stop an app asynchronously."""
        try:
            await self.hop3_app.api_client.stop_app(app_name)
            self.notify(f"[yellow]Stopped {app_name}[/]")
            self._refresh_apps()
        except Exception as e:
            self.notify(f"Failed to stop {app_name}: {e}", severity="error")

    def action_restart_app(self) -> None:
        """Restart the selected application."""
        app_name = self._get_selected_app_name()
        if app_name:
            self.notify(f"Restarting {app_name}...")
            self.run_worker(self._restart_app(app_name))

    async def _restart_app(self, app_name: str) -> None:
        """Restart an app asynchronously."""
        try:
            await self.hop3_app.api_client.restart_app(app_name)
            self.notify(f"[green]Restarted {app_name}[/]")
            self._refresh_apps()
        except Exception as e:
            self.notify(f"Failed to restart {app_name}: {e}", severity="error")

    def action_new_app(self) -> None:
        """Create a new application."""
        self.notify("New app dialog not yet implemented")

    def action_refresh(self) -> None:
        """Refresh the apps list."""
        self._refresh_apps()
        self.notify("Refreshing apps list...")
