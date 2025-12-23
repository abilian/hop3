# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Backups management screen."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from hop3_tui.api.models import Backup
from hop3_tui.widgets.confirmation import ConfirmationDialog

if TYPE_CHECKING:
    from hop3_tui.app import Hop3TUI


class CreateBackupDialog(Static):
    """Dialog for creating a new backup."""

    DEFAULT_CSS = """
    CreateBackupDialog {
        align: center middle;
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: solid $primary;
    }

    CreateBackupDialog #dialog-title {
        text-style: bold;
        margin-bottom: 1;
    }

    CreateBackupDialog .field-label {
        margin-top: 1;
    }

    CreateBackupDialog Input {
        margin-bottom: 1;
        width: 100%;
    }

    CreateBackupDialog #button-row {
        margin-top: 1;
        align: center middle;
    }

    CreateBackupDialog Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Create Backup", id="dialog-title")
        yield Label("App Name:", classes="field-label")
        yield Input(placeholder="app-name", id="app-name-input")
        with Horizontal(id="button-row"):
            yield Button("Create", id="btn-create", variant="primary")
            yield Button("Cancel", id="btn-cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-create":
            app_input = self.query_one("#app-name-input", Input)
            app_name = app_input.value.strip()

            if not app_name:
                self.app.notify("App name is required", severity="error")
                return

            self.post_message(BackupCreated(app_name))
        else:
            self.post_message(BackupDialogCancelled())


class BackupCreated(Message):
    """Message posted when a backup creation is requested."""

    def __init__(self, app_name: str) -> None:
        super().__init__()
        self.app_name = app_name


class BackupDialogCancelled(Message):
    """Message posted when a dialog is cancelled."""


class BackupsScreen(Screen):
    """Screen for viewing and managing backups."""

    CSS = """
    BackupsScreen {
        layout: vertical;
    }

    #backups-header {
        height: 3;
        padding: 0 1;
        background: $primary-darken-2;
    }

    #backups-title {
        text-style: bold;
    }

    #backups-table-container {
        height: 1fr;
        padding: 1;
    }

    #backups-table {
        height: 1fr;
    }

    #backups-actions {
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    #backup-details {
        height: 8;
        padding: 1;
        background: $surface;
        border-top: solid $primary;
    }

    #backup-details-title {
        text-style: bold;
        margin-bottom: 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back"),
        Binding("n", "new_backup", "New"),
        Binding("r", "restore_backup", "Restore"),
        Binding("d", "delete_backup", "Delete"),
        Binding("R", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._backups: list[Backup] = []
        self._dialog_open: bool = False

    @property
    def hop3_app(self) -> Hop3TUI | None:
        """Get the Hop3TUI app instance if available."""
        if hasattr(self.app, "api_client"):
            return self.app  # type: ignore[return-value]
        return None

    def compose(self) -> ComposeResult:
        yield Header()
        with Static(id="backups-header"):
            yield Static("Backups", id="backups-title")
        with Vertical(id="backups-table-container"):
            yield DataTable(id="backups-table")
        with Static(id="backup-details"):
            yield Static("DETAILS", id="backup-details-title")
            yield Static("Select a backup to view details", id="backup-details-content")
        with Horizontal(id="backups-actions"):
            yield Static("[n] New  [r] Restore  [d] Delete  [R] Refresh  [Esc] Back")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the backups table."""
        table = self.query_one("#backups-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("ID", "APP", "SIZE", "CREATED", "ADDONS")
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Refresh backups from server."""
        self.run_worker(self._fetch_backups(), exclusive=True)

    async def _fetch_backups(self) -> None:
        """Fetch backups from server asynchronously."""
        if not self.hop3_app:
            # No API client available, use mock data
            now = datetime.now(timezone.utc)
            self._backups = [
                Backup(
                    id="20240315_120000",
                    app_name="myapp",
                    created_at=now,
                    size_bytes=52428800,
                    addons=["postgresql"],
                ),
                Backup(
                    id="20240314_080000",
                    app_name="myapp",
                    created_at=now,
                    size_bytes=51380224,
                    addons=["postgresql"],
                ),
                Backup(
                    id="20240310_160000",
                    app_name="api-server",
                    created_at=now,
                    size_bytes=104857600,
                    addons=["postgresql", "redis"],
                ),
                Backup(
                    id="20240301_000000",
                    app_name="worker",
                    created_at=now,
                    size_bytes=10485760,
                    addons=[],
                ),
            ]
            self._update_table()
            return

        try:
            self._backups = await self.hop3_app.api_client.list_backups()
            self._update_table()
        except Exception as e:
            self.notify(f"Failed to fetch backups: {e}", severity="error", timeout=5)

    def _update_table(self) -> None:
        """Update the table with current backups."""
        table = self.query_one("#backups-table", DataTable)
        table.clear()

        for backup in sorted(self._backups, key=lambda b: b.id, reverse=True):
            size_str = self._format_size(backup.size_bytes)
            created_str = self._format_date(backup.created_at)
            addons_str = ", ".join(backup.addons) if backup.addons else "[dim]none[/]"

            table.add_row(
                backup.id,
                backup.app_name,
                size_str,
                created_str,
                addons_str,
                key=backup.id,
            )

    def _format_size(self, bytes_size: int) -> str:
        """Format bytes into human-readable size."""
        if bytes_size < 1024:
            return f"{bytes_size} B"
        if bytes_size < 1024 * 1024:
            return f"{bytes_size / 1024:.1f} KB"
        if bytes_size < 1024 * 1024 * 1024:
            return f"{bytes_size / (1024 * 1024):.1f} MB"
        return f"{bytes_size / (1024 * 1024 * 1024):.1f} GB"

    def _format_date(self, dt: datetime | None) -> str:
        """Format datetime for display."""
        if not dt:
            return "N/A"
        return dt.strftime("%Y-%m-%d %H:%M")

    def _get_selected_backup(self) -> Backup | None:
        """Get the currently selected backup."""
        table = self.query_one("#backups-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            backup_id = str(table.get_cell_at((table.cursor_row, 0)))
            for backup in self._backups:
                if backup.id == backup_id:
                    return backup
        return None

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update details panel when row changes."""
        backup = self._get_selected_backup()
        details_content = self.query_one("#backup-details-content", Static)

        if backup:
            addons_list = ", ".join(backup.addons) if backup.addons else "none"
            details_content.update(
                f"ID: {backup.id}\n"
                f"App: {backup.app_name}    Size: {self._format_size(backup.size_bytes)}    "
                f"Addons: {addons_list}"
            )
        else:
            details_content.update("Select a backup to view details")

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.app.switch_mode("dashboard")

    def action_new_backup(self) -> None:
        """Create a new backup."""
        if self._dialog_open:
            return
        dialog = CreateBackupDialog()
        self.mount(dialog)
        self._dialog_open = True

    def action_restore_backup(self) -> None:
        """Restore the selected backup."""
        backup = self._get_selected_backup()
        if not backup:
            self.notify("No backup selected", severity="warning")
            return

        dialog = ConfirmationDialog(
            title="Restore Backup",
            message=(
                f"Restore backup {backup.id} for {backup.app_name}?\n"
                "This will replace the current app state."
            ),
            confirm_label="Restore",
            cancel_label="Cancel",
        )
        self.mount(dialog)
        self._pending_action = ("restore", backup)

    def action_delete_backup(self) -> None:
        """Delete the selected backup."""
        backup = self._get_selected_backup()
        if not backup:
            self.notify("No backup selected", severity="warning")
            return

        dialog = ConfirmationDialog(
            title="Delete Backup",
            message=f"Delete backup {backup.id}?\nThis cannot be undone.",
            confirm_label="Delete",
            cancel_label="Cancel",
        )
        self.mount(dialog)
        self._pending_action = ("delete", backup)

    def action_refresh(self) -> None:
        """Refresh the backups list."""
        self._refresh_data()
        self.notify("Refreshing backups...")

    def on_backup_created(self, event: BackupCreated) -> None:
        """Handle backup creation request."""
        self._close_dialog(CreateBackupDialog)
        self.run_worker(self._create_backup(event.app_name))

    async def _create_backup(self, app_name: str) -> None:
        """Create a backup."""
        self.notify(f"Creating backup for {app_name}...")

        if not self.hop3_app:
            # Mock create
            new_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            self._backups.append(
                Backup(
                    id=new_id,
                    app_name=app_name,
                    created_at=datetime.now(timezone.utc),
                    size_bytes=10485760,
                    addons=[],
                )
            )
            self._update_table()
            self.notify(f"[green]Created backup {new_id}[/]")
            return

        try:
            backup_id = await self.hop3_app.api_client.create_backup(app_name)
            self.notify(f"[green]Created backup {backup_id}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to create backup: {e}", severity="error")

    def on_backup_dialog_cancelled(self, event: BackupDialogCancelled) -> None:
        """Handle dialog cancellation."""
        self._close_dialog(CreateBackupDialog)

    def on_confirmation_dialog_confirmed(
        self, event: ConfirmationDialog.Confirmed
    ) -> None:
        """Handle confirmation."""
        self._close_dialog(ConfirmationDialog)

        if hasattr(self, "_pending_action"):
            action, backup = self._pending_action
            if action == "restore":
                self.run_worker(self._restore_backup(backup.id, backup.app_name))
            elif action == "delete":
                self.run_worker(self._delete_backup(backup.id))
            del self._pending_action

    def on_confirmation_dialog_cancelled(
        self, event: ConfirmationDialog.Cancelled
    ) -> None:
        """Handle confirmation cancellation."""
        self._close_dialog(ConfirmationDialog)
        if hasattr(self, "_pending_action"):
            del self._pending_action

    async def _restore_backup(self, backup_id: str, app_name: str) -> None:
        """Restore a backup."""
        self.notify(f"Restoring {backup_id}...")

        if not self.hop3_app:
            # Mock restore
            self.notify(f"[green]Restored {app_name} from {backup_id}[/]")
            return

        try:
            await self.hop3_app.api_client.restore_backup(backup_id)
            self.notify(f"[green]Restored {app_name} from {backup_id}[/]")
        except Exception as e:
            self.notify(f"Failed to restore backup: {e}", severity="error")

    async def _delete_backup(self, backup_id: str) -> None:
        """Delete a backup."""
        if not self.hop3_app:
            # Mock delete
            self._backups = [b for b in self._backups if b.id != backup_id]
            self._update_table()
            self.notify(f"[red]Deleted {backup_id}[/]")
            return

        try:
            await self.hop3_app.api_client.delete_backup(backup_id)
            self.notify(f"[red]Deleted {backup_id}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to delete backup: {e}", severity="error")

    def _close_dialog(self, dialog_type: type) -> None:
        """Close dialogs of a given type."""
        dialogs = self.query(dialog_type)
        for dialog in dialogs:
            dialog.remove()
        self._dialog_open = False
