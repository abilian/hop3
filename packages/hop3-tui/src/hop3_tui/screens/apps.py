# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Applications list screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static

from hop3_tui.api.models import App, AppState


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

    BINDINGS = [
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
        self.set_interval(10, self._refresh_apps)

    def _refresh_apps(self) -> None:
        """Refresh apps list from server."""
        # TODO: Fetch from API
        # For now, use mock data
        self._apps = [
            App(name="myapp", state=AppState.RUNNING, port=8000, runtime="uwsgi"),
            App(name="api-server", state=AppState.RUNNING, port=8001, runtime="uwsgi"),
            App(name="worker", state=AppState.STOPPED, runtime="uwsgi"),
            App(name="frontend", state=AppState.RUNNING, port=8002, runtime="static"),
            App(name="broken-app", state=AppState.FAILED, runtime="uwsgi"),
        ]
        self._update_table()

    def _update_table(self, filter_text: str = "") -> None:
        """Update the table with current apps."""
        table = self.query_one("#apps-table", DataTable)
        table.clear()

        for app in self._apps:
            if filter_text and filter_text.lower() not in app.name.lower():
                continue

            status_style = self._get_status_style(app.state)
            port_str = str(app.port) if app.port else "-"
            updated = "N/A"  # TODO: Format datetime

            table.add_row(
                app.name,
                f"[{status_style}]{app.state.value}[/]",
                port_str,
                app.runtime,
                updated,
                key=app.name,
            )

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

    def _get_selected_app(self) -> App | None:
        """Get the currently selected app."""
        table = self.query_one("#apps-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self._apps):
            row_key = table.get_row_at(table.cursor_row)
            # Find app by name
            for app in self._apps:
                if app.name == table.get_row_key(table.cursor_row):
                    return app
        return None

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes."""
        if event.input.id == "filter-input":
            self._update_table(event.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (Enter key)."""
        self.action_view_app()

    def action_focus_filter(self) -> None:
        """Focus the filter input."""
        self.query_one("#filter-input", Input).focus()

    def action_view_app(self) -> None:
        """View the selected application."""
        table = self.query_one("#apps-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            row_key = table.get_row_at(table.cursor_row)
            app_name = str(table.get_cell_at((table.cursor_row, 0)))
            self.app.push_screen("app_detail", {"app_name": app_name})

    def action_start_app(self) -> None:
        """Start the selected application."""
        table = self.query_one("#apps-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            app_name = str(table.get_cell_at((table.cursor_row, 0)))
            self.notify(f"Starting {app_name}...")
            # TODO: Call API

    def action_stop_app(self) -> None:
        """Stop the selected application."""
        table = self.query_one("#apps-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            app_name = str(table.get_cell_at((table.cursor_row, 0)))
            self.notify(f"Stopping {app_name}...")
            # TODO: Call API with confirmation

    def action_restart_app(self) -> None:
        """Restart the selected application."""
        table = self.query_one("#apps-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            app_name = str(table.get_cell_at((table.cursor_row, 0)))
            self.notify(f"Restarting {app_name}...")
            # TODO: Call API

    def action_new_app(self) -> None:
        """Create a new application."""
        self.notify("New app dialog not yet implemented")

    def action_refresh(self) -> None:
        """Refresh the apps list."""
        self._refresh_apps()
        self.notify("Apps list refreshed")
