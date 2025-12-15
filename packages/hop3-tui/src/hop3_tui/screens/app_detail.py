# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Application detail screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from hop3_tui.api.models import App, AppState


class AppInfoPanel(Static):
    """Panel showing application information."""

    def __init__(self, app: App) -> None:
        super().__init__()
        self._app = app

    def compose(self) -> ComposeResult:
        yield Static("INFORMATION", classes="panel-title")
        yield Static(id="app-info-content")

    def on_mount(self) -> None:
        self._update_display()

    def update_app(self, app: App) -> None:
        self._app = app
        self._update_display()

    def _update_display(self) -> None:
        content = self.query_one("#app-info-content", Static)
        port_str = str(self._app.port) if self._app.port else "N/A"
        hostname = self._app.hostname or "N/A"

        content.update(
            f"Runtime:    {self._app.runtime}\n"
            f"Port:       {port_str}\n"
            f"Hostname:   {hostname}\n"
            f"Workers:    {self._app.workers}\n"
        )


class AppActionsPanel(Static):
    """Panel showing application actions."""

    def __init__(self, app: App) -> None:
        super().__init__()
        self._app = app

    def compose(self) -> ComposeResult:
        yield Static("ACTIONS", classes="panel-title")
        with Vertical(id="action-buttons"):
            if self._app.state == AppState.RUNNING:
                yield Button("Stop", id="btn-stop", variant="warning")
                yield Button("Restart", id="btn-restart", variant="primary")
            else:
                yield Button("Start", id="btn-start", variant="success")
            yield Button("Deploy", id="btn-deploy", variant="primary")
            yield Button("Backup", id="btn-backup", variant="default")
            yield Button("Destroy", id="btn-destroy", variant="error")


class AppLogsPreview(Static):
    """Panel showing recent logs preview."""

    def compose(self) -> ComposeResult:
        yield Static("RECENT LOGS", classes="panel-title")
        yield Static(
            "[dim]Loading logs...[/dim]",
            id="logs-preview-content",
        )

    def update_logs(self, logs: list[str]) -> None:
        content = self.query_one("#logs-preview-content", Static)
        if logs:
            content.update("\n".join(logs[-5:]))
        else:
            content.update("[dim]No logs available[/dim]")


class AppDetailScreen(Screen):
    """Screen showing details for a single application."""

    CSS = """
    AppDetailScreen {
        layout: vertical;
    }

    #app-header {
        height: 3;
        padding: 0 1;
        background: $primary-darken-2;
    }

    #app-name {
        text-style: bold;
    }

    #app-status {
        dock: right;
    }

    #main-content {
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
        padding: 1;
        height: 1fr;
    }

    .panel {
        border: solid $primary;
        padding: 1;
    }

    .panel-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #info-panel {
        row-span: 1;
    }

    #actions-panel {
        row-span: 1;
    }

    #related-panel {
        column-span: 2;
        height: auto;
    }

    #logs-panel {
        column-span: 2;
        height: 1fr;
    }

    #action-buttons {
        height: auto;
    }

    #action-buttons Button {
        margin-bottom: 1;
        width: 100%;
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
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("l", "view_logs", "Logs"),
        Binding("e", "view_env", "Env Vars"),
        Binding("s", "stop_app", "Stop"),
        Binding("r", "restart_app", "Restart"),
        Binding("R", "refresh", "Refresh"),
    ]

    def __init__(self, app_name: str = "") -> None:
        super().__init__()
        self.app_name = app_name
        self._app: App | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="app-header"):
            yield Static(f"App: {self.app_name}", id="app-name")
            yield Static("LOADING", id="app-status")
        with Container(id="main-content"):
            # Create placeholder app for initial render
            placeholder_app = App(name=self.app_name)
            with Container(id="info-panel", classes="panel"):
                yield AppInfoPanel(placeholder_app)
            with Container(id="actions-panel", classes="panel"):
                yield AppActionsPanel(placeholder_app)
            with Container(id="related-panel", classes="panel"):
                yield Static("RELATED", classes="panel-title")
                yield Static("[l] Logs     [e] Env Vars     [a] Addons     [B] Backups")
            with Container(id="logs-panel", classes="panel"):
                yield AppLogsPreview()
        yield Footer()

    def on_mount(self) -> None:
        """Load application data."""
        self._refresh_data()
        self.set_interval(3, self._refresh_data)

    def _refresh_data(self) -> None:
        """Refresh application data from server."""
        # TODO: Fetch from API
        # Mock data for now
        self._app = App(
            name=self.app_name,
            state=AppState.RUNNING,
            port=8000,
            runtime="uwsgi",
            hostname=f"{self.app_name}.example.com",
            workers=2,
        )
        self._update_display()

    def _update_display(self) -> None:
        """Update the display with current app data."""
        if not self._app:
            return

        # Update status
        status = self.query_one("#app-status", Static)
        status_style = self._get_status_style(self._app.state)
        status.update(f"[{status_style}]{self._app.state.value}[/]")

        # Update info panel
        info_panel = self.query_one(AppInfoPanel)
        info_panel.update_app(self._app)

        # Update logs preview
        logs_preview = self.query_one(AppLogsPreview)
        logs_preview.update_logs([
            "10:32:15 [INFO] Request processed in 45ms",
            "10:32:14 [INFO] GET /api/users 200",
            "10:32:10 [INFO] Database query completed",
        ])

    def _get_status_style(self, state: AppState) -> str:
        """Get the style for a status."""
        match state:
            case AppState.RUNNING:
                return "green"
            case AppState.STOPPED:
                return "dim"
            case AppState.FAILED:
                return "red"
            case _:
                return "yellow"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        match event.button.id:
            case "btn-start":
                self.action_start_app()
            case "btn-stop":
                self.action_stop_app()
            case "btn-restart":
                self.action_restart_app()
            case "btn-deploy":
                self.notify("Deploy not yet implemented")
            case "btn-backup":
                self.notify(f"Creating backup of {self.app_name}...")
            case "btn-destroy":
                self.notify("Destroy requires confirmation (not implemented)")

    def action_go_back(self) -> None:
        """Go back to apps list."""
        self.app.switch_mode("apps")

    def action_view_logs(self) -> None:
        """View full logs."""
        self.app.push_screen("logs", {"app_name": self.app_name})

    def action_view_env(self) -> None:
        """View environment variables."""
        self.notify("Env vars screen not yet implemented")

    def action_start_app(self) -> None:
        """Start the application."""
        self.notify(f"Starting {self.app_name}...")
        # TODO: Call API

    def action_stop_app(self) -> None:
        """Stop the application."""
        self.notify(f"Stopping {self.app_name}...")
        # TODO: Call API with confirmation

    def action_restart_app(self) -> None:
        """Restart the application."""
        self.notify(f"Restarting {self.app_name}...")
        # TODO: Call API

    def action_refresh(self) -> None:
        """Refresh application data."""
        self._refresh_data()
        self.notify("Refreshed")
