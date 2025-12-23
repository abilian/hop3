# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Application detail screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from hop3_tui.api.models import App, AppState
from hop3_tui.widgets.confirmation import ConfirmationDialog

if TYPE_CHECKING:
    from hop3_tui.app import Hop3TUI


class DeployDialog(Static):
    """Dialog for deploying from git URL."""

    DEFAULT_CSS = """
    DeployDialog {
        align: center middle;
        width: 70;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: solid $primary;
    }

    DeployDialog #dialog-title {
        text-style: bold;
        margin-bottom: 1;
    }

    DeployDialog .field-label {
        margin-top: 1;
    }

    DeployDialog .field-hint {
        color: $text-muted;
        margin-bottom: 1;
    }

    DeployDialog Input {
        width: 100%;
    }

    DeployDialog #button-row {
        margin-top: 2;
        align: center middle;
    }

    DeployDialog Button {
        margin: 0 1;
    }
    """

    def __init__(self, app_name: str) -> None:
        super().__init__()
        self.app_name = app_name

    def compose(self) -> ComposeResult:
        yield Static(f"Deploy {self.app_name}", id="dialog-title")
        yield Label("Git URL:", classes="field-label")
        yield Input(
            placeholder="https://github.com/user/repo.git",
            id="git-url-input",
        )
        yield Static(
            "Enter the git repository URL to deploy from", classes="field-hint"
        )
        with Horizontal(id="button-row"):
            yield Button("Deploy", id="btn-deploy-confirm", variant="primary")
            yield Button("Cancel", id="btn-cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-deploy-confirm":
            url_input = self.query_one("#git-url-input", Input)
            git_url = url_input.value.strip()

            if not git_url:
                self.app.notify("Git URL is required", severity="error")
                return

            self.post_message(DeployRequested(self.app_name, git_url))
        else:
            self.post_message(DeployDialogCancelled())


class DeployRequested(Message):
    """Message posted when deploy is requested."""

    def __init__(self, app_name: str, git_url: str) -> None:
        super().__init__()
        self.app_name = app_name
        self.git_url = git_url


class DeployDialogCancelled(Message):
    """Message posted when deploy dialog is cancelled."""


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

    BINDINGS: ClassVar[list[Binding]] = [
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
        self._dialog_open: bool = False

    @property
    def hop3_app(self) -> Hop3TUI | None:
        """Get the Hop3TUI app instance if available."""
        if hasattr(self.app, "api_client"):
            return self.app  # type: ignore[return-value]
        return None

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
                self.action_deploy()
            case "btn-backup":
                self.action_backup()
            case "btn-destroy":
                self.action_destroy()

    def action_go_back(self) -> None:
        """Go back to apps list."""
        self.app.switch_mode("apps")

    def action_view_logs(self) -> None:
        """View full logs."""
        self.app.push_screen("logs", {"app_name": self.app_name})

    def action_view_env(self) -> None:
        """View environment variables."""
        if hasattr(self.app, "push_env_vars"):
            self.app.push_env_vars(self.app_name)
        else:
            self.notify("Env vars screen not available")

    def action_start_app(self) -> None:
        """Start the application."""
        self.notify(f"Starting {self.app_name}...")
        self.run_worker(self._start_app())

    async def _start_app(self) -> None:
        """Start the app via API."""
        if not self.hop3_app:
            return
        try:
            await self.hop3_app.api_client.start_app(self.app_name)
            self.notify(f"[green]Started {self.app_name}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to start: {e}", severity="error")

    def action_stop_app(self) -> None:
        """Stop the application with confirmation."""
        dialog = ConfirmationDialog(
            title="Stop Application",
            message=f"Are you sure you want to stop {self.app_name}?",
            confirm_label="Stop",
            cancel_label="Cancel",
        )
        self.mount(dialog)
        self._pending_action = "stop"

    async def _stop_app(self) -> None:
        """Stop the app via API."""
        if not self.hop3_app:
            return
        try:
            await self.hop3_app.api_client.stop_app(self.app_name)
            self.notify(f"[yellow]Stopped {self.app_name}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to stop: {e}", severity="error")

    def action_restart_app(self) -> None:
        """Restart the application."""
        self.notify(f"Restarting {self.app_name}...")
        self.run_worker(self._restart_app())

    async def _restart_app(self) -> None:
        """Restart the app via API."""
        if not self.hop3_app:
            return
        try:
            await self.hop3_app.api_client.restart_app(self.app_name)
            self.notify(f"[green]Restarted {self.app_name}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to restart: {e}", severity="error")

    def action_deploy(self) -> None:
        """Deploy the application from git."""
        if self._dialog_open:
            return
        dialog = DeployDialog(self.app_name)
        self.mount(dialog)
        self._dialog_open = True

    def on_deploy_requested(self, event: DeployRequested) -> None:
        """Handle deploy request."""
        self._close_dialog(DeployDialog)
        self.notify(f"Deploying {event.app_name} from {event.git_url}...")
        self.run_worker(self._deploy_app(event.git_url))

    async def _deploy_app(self, git_url: str) -> None:
        """Deploy the app via API."""
        if not self.hop3_app:
            self.notify("[yellow]API not available - deploy simulated[/]")
            return
        try:
            await self.hop3_app.api_client.deploy_app(self.app_name, git_url)
            self.notify(f"[green]Deployed {self.app_name}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to deploy: {e}", severity="error")

    def on_deploy_dialog_cancelled(self, event: DeployDialogCancelled) -> None:
        """Handle deploy dialog cancellation."""
        self._close_dialog(DeployDialog)

    def action_backup(self) -> None:
        """Create a backup of the application."""
        self.notify(f"Creating backup of {self.app_name}...")
        self.run_worker(self._create_backup())

    async def _create_backup(self) -> None:
        """Create backup via API."""
        if not self.hop3_app:
            self.notify("[yellow]API not available - backup simulated[/]")
            return
        try:
            backup_id = await self.hop3_app.api_client.create_backup(self.app_name)
            self.notify(f"[green]Backup created: {backup_id}[/]")
        except Exception as e:
            self.notify(f"Failed to create backup: {e}", severity="error")

    def action_destroy(self) -> None:
        """Destroy the application with confirmation."""
        dialog = ConfirmationDialog(
            title="Destroy Application",
            message=f"Are you sure you want to DESTROY {self.app_name}?\n"
            "This will delete all data and cannot be undone!",
            confirm_label="Destroy",
            cancel_label="Cancel",
        )
        self.mount(dialog)
        self._pending_action = "destroy"

    def on_confirmation_dialog_confirmed(
        self, event: ConfirmationDialog.Confirmed
    ) -> None:
        """Handle confirmation dialog confirmation."""
        self._close_dialog(ConfirmationDialog)
        if hasattr(self, "_pending_action"):
            if self._pending_action == "stop":
                self.notify(f"Stopping {self.app_name}...")
                self.run_worker(self._stop_app())
            elif self._pending_action == "destroy":
                self.notify(f"Destroying {self.app_name}...")
                self.run_worker(self._destroy_app())
            del self._pending_action

    def on_confirmation_dialog_cancelled(
        self, event: ConfirmationDialog.Cancelled
    ) -> None:
        """Handle confirmation dialog cancellation."""
        self._close_dialog(ConfirmationDialog)
        if hasattr(self, "_pending_action"):
            del self._pending_action

    async def _destroy_app(self) -> None:
        """Destroy the app via API."""
        if not self.hop3_app:
            self.notify("[yellow]API not available - destroy simulated[/]")
            return
        try:
            await self.hop3_app.api_client.delete_app(self.app_name)
            self.notify(f"[red]Destroyed {self.app_name}[/]")
            # Go back to apps list
            self.app.switch_mode("apps")
        except Exception as e:
            self.notify(f"Failed to destroy: {e}", severity="error")

    def _close_dialog(self, dialog_type: type) -> None:
        """Close dialogs of a given type."""
        dialogs = self.query(dialog_type)
        for dialog in dialogs:
            dialog.remove()
        self._dialog_open = False

    def action_refresh(self) -> None:
        """Refresh application data."""
        self._refresh_data()
        self.notify("Refreshed")
