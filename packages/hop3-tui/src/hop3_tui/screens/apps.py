# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Applications list screen."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from hop3_tui.api.models import App, AppState
from hop3_tui.widgets.confirmation import ConfirmationDialog

if TYPE_CHECKING:
    from hop3_tui.app import Hop3TUI


class NewAppDialog(Static):
    """Dialog for creating a new application."""

    DEFAULT_CSS = """
    NewAppDialog {
        align: center middle;
        width: 70;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: solid $primary;
    }

    NewAppDialog #dialog-title {
        text-style: bold;
        margin-bottom: 1;
    }

    NewAppDialog .field-label {
        margin-top: 1;
    }

    NewAppDialog .field-hint {
        color: $text-muted;
        margin-bottom: 1;
    }

    NewAppDialog Input {
        margin-bottom: 0;
        width: 100%;
    }

    NewAppDialog #button-row {
        margin-top: 2;
        align: center middle;
    }

    NewAppDialog Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Create New Application", id="dialog-title")
        yield Label("App Name:", classes="field-label")
        yield Input(placeholder="my-app", id="app-name-input")
        yield Static(
            "Use lowercase letters, numbers, and hyphens", classes="field-hint"
        )
        yield Label("Git URL (optional):", classes="field-label")
        yield Input(placeholder="https://github.com/user/repo.git", id="git-url-input")
        yield Static("Leave empty to create an empty app", classes="field-hint")
        with Horizontal(id="button-row"):
            yield Button("Create", id="btn-create", variant="primary")
            yield Button("Cancel", id="btn-cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-create":
            name_input = self.query_one("#app-name-input", Input)
            url_input = self.query_one("#git-url-input", Input)

            app_name = name_input.value.strip()
            git_url = url_input.value.strip()

            if not app_name:
                self.app.notify("App name is required", severity="error")
                return

            # Validate app name format
            if not all(c.isalnum() or c == "-" for c in app_name):
                self.app.notify(
                    "App name must contain only letters, numbers, and hyphens",
                    severity="error",
                )
                return

            if app_name[0].isdigit() or app_name[0] == "-":
                self.app.notify("App name must start with a letter", severity="error")
                return

            self.post_message(NewAppCreated(app_name, git_url or None))
        else:
            self.post_message(NewAppDialogCancelled())


class NewAppCreated(Message):
    """Message posted when a new app is created."""

    def __init__(self, app_name: str, git_url: str | None) -> None:
        super().__init__()
        self.app_name = app_name
        self.git_url = git_url


class NewAppDialogCancelled(Message):
    """Message posted when the new app dialog is cancelled."""


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
        Binding("escape", "go_back", "Back"),
        Binding("enter", "view_app", "View"),
        Binding("s", "start_app", "Start"),
        Binding("S", "stop_app", "Stop"),
        Binding("r", "restart_app", "Restart"),
        Binding("D", "delete_app", "Delete"),
        Binding("n", "new_app", "New"),
        Binding("/", "focus_filter", "Filter"),
        Binding("R", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._apps: list[App] = []
        self._filter_text: str = ""
        self._dialog_open: bool = False

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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in the filter input - move focus to table."""
        if event.input.id == "filter-input":
            self.query_one("#apps-table", DataTable).focus()

    def action_go_back(self) -> None:
        """Go back to dashboard."""
        self.app.switch_mode("dashboard")

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Check if action should run - intercept escape when filter focused."""
        if action == "go_back":
            filter_input = self.query_one("#filter-input", Input)
            if filter_input.has_focus:
                # Don't go back, just unfocus filter
                self.query_one("#apps-table", DataTable).focus()
                return False  # Prevent the action
        return True

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
            dialog = ConfirmationDialog(
                title="Stop Application",
                message=f"Are you sure you want to stop {app_name}?",
                confirm_label="Stop",
                cancel_label="Cancel",
            )
            self.mount(dialog)
            self._pending_action = ("stop", app_name)

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

    def action_delete_app(self) -> None:
        """Delete the selected application."""
        app_name = self._get_selected_app_name()
        if app_name:
            dialog = ConfirmationDialog(
                title="Delete Application",
                message=f"Are you sure you want to delete {app_name}?\nThis action cannot be undone.",
                confirm_label="Delete",
                cancel_label="Cancel",
            )
            self.mount(dialog)
            self._pending_action = ("delete", app_name)

    def action_new_app(self) -> None:
        """Create a new application."""
        if self._dialog_open:
            return
        dialog = NewAppDialog()
        self.mount(dialog)
        self._dialog_open = True

    def action_refresh(self) -> None:
        """Refresh the apps list."""
        self._refresh_apps()
        self.notify("Refreshing apps list...")

    def on_confirmation_dialog_confirmed(
        self, event: ConfirmationDialog.Confirmed
    ) -> None:
        """Handle confirmation dialog confirmation."""
        dialogs = self.query(ConfirmationDialog)
        for dialog in dialogs:
            dialog.remove()

        if hasattr(self, "_pending_action"):
            action, app_name = self._pending_action
            if action == "stop":
                self.notify(f"Stopping {app_name}...")
                self.run_worker(self._stop_app(app_name))
            elif action == "delete":
                self.notify(f"Deleting {app_name}...")
                self.run_worker(self._delete_app(app_name))
            del self._pending_action

    def on_confirmation_dialog_cancelled(
        self, event: ConfirmationDialog.Cancelled
    ) -> None:
        """Handle confirmation dialog cancellation."""
        dialogs = self.query(ConfirmationDialog)
        for dialog in dialogs:
            dialog.remove()
        if hasattr(self, "_pending_action"):
            del self._pending_action

    async def _delete_app(self, app_name: str) -> None:
        """Delete an app asynchronously."""
        try:
            await self.hop3_app.api_client.delete_app(app_name)
            self.notify(f"[red]Deleted {app_name}[/]")
            self._refresh_apps()
        except Exception as e:
            self.notify(f"Failed to delete {app_name}: {e}", severity="error")

    def on_new_app_created(self, event: NewAppCreated) -> None:
        """Handle new app creation."""
        self._close_dialog(NewAppDialog)
        if event.git_url:
            self.notify(f"Deploying {event.app_name} from {event.git_url}...")
            self.run_worker(self._deploy_app(event.app_name, event.git_url))
        else:
            self.notify(f"Creating {event.app_name}...")
            self.run_worker(self._create_app(event.app_name))

    async def _create_app(self, app_name: str) -> None:
        """Create an empty app."""
        if not self.hop3_app:
            self.notify("[yellow]API not available - app creation simulated[/]")
            return
        try:
            await self.hop3_app.api_client.create_app(app_name)
            self.notify(f"[green]Created {app_name}[/]")
            self._refresh_apps()
        except Exception as e:
            self.notify(f"Failed to create {app_name}: {e}", severity="error")

    async def _deploy_app(self, app_name: str, git_url: str) -> None:
        """Deploy a new app from git URL."""
        try:
            await self.hop3_app.api_client.deploy_app(app_name, git_url)
            self.notify(f"[green]Deployed {app_name}[/]")
            self._refresh_apps()
        except Exception as e:
            self.notify(f"Failed to deploy {app_name}: {e}", severity="error")

    def on_new_app_dialog_cancelled(self, event: NewAppDialogCancelled) -> None:
        """Handle new app dialog cancellation."""
        self._close_dialog(NewAppDialog)

    def _close_dialog(self, dialog_type: type) -> None:
        """Close dialogs of a given type."""
        dialogs = self.query(dialog_type)
        for dialog in dialogs:
            dialog.remove()
        self._dialog_open = False
