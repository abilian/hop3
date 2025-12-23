# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Addons management screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
)

from hop3_tui.widgets.confirmation import ConfirmationDialog

if TYPE_CHECKING:
    from hop3_tui.app import Hop3TUI

# Available addon types
ADDON_TYPES = [
    ("postgresql", "PostgreSQL Database"),
    ("redis", "Redis Cache"),
    ("mysql", "MySQL Database"),
    ("mongodb", "MongoDB Database"),
    ("s3", "S3 Storage"),
]


class CreateAddonDialog(Static):
    """Dialog for creating a new addon."""

    DEFAULT_CSS = """
    CreateAddonDialog {
        align: center middle;
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: solid $primary;
    }

    CreateAddonDialog #dialog-title {
        text-style: bold;
        margin-bottom: 1;
    }

    CreateAddonDialog .field-label {
        margin-top: 1;
    }

    CreateAddonDialog Input, CreateAddonDialog Select {
        margin-bottom: 1;
        width: 100%;
    }

    CreateAddonDialog #button-row {
        margin-top: 1;
        align: center middle;
    }

    CreateAddonDialog Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Create New Addon", id="dialog-title")
        yield Label("Type:", classes="field-label")
        yield Select(
            [(label, value) for value, label in ADDON_TYPES],
            id="addon-type-select",
            prompt="Select addon type",
        )
        yield Label("Name:", classes="field-label")
        yield Input(placeholder="addon-name", id="addon-name-input")
        with Horizontal(id="button-row"):
            yield Button("Create", id="btn-create", variant="primary")
            yield Button("Cancel", id="btn-cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-create":
            type_select = self.query_one("#addon-type-select", Select)
            name_input = self.query_one("#addon-name-input", Input)

            addon_type = type_select.value
            addon_name = name_input.value.strip()

            if addon_type == Select.BLANK:
                self.app.notify("Please select an addon type", severity="error")
                return

            if not addon_name:
                self.app.notify("Addon name is required", severity="error")
                return

            self.post_message(AddonCreated(str(addon_type), addon_name))
        else:
            self.post_message(AddonDialogCancelled())


class AttachAddonDialog(Static):
    """Dialog for attaching an addon to an app."""

    DEFAULT_CSS = """
    AttachAddonDialog {
        align: center middle;
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: solid $primary;
    }

    AttachAddonDialog #dialog-title {
        text-style: bold;
        margin-bottom: 1;
    }

    AttachAddonDialog .field-label {
        margin-top: 1;
    }

    AttachAddonDialog Input {
        margin-bottom: 1;
        width: 100%;
    }

    AttachAddonDialog #button-row {
        margin-top: 1;
        align: center middle;
    }

    AttachAddonDialog Button {
        margin: 0 1;
    }
    """

    def __init__(self, addon_name: str) -> None:
        super().__init__()
        self.addon_name = addon_name

    def compose(self) -> ComposeResult:
        yield Static(f"Attach {self.addon_name}", id="dialog-title")
        yield Label("App Name:", classes="field-label")
        yield Input(placeholder="app-name", id="app-name-input")
        with Horizontal(id="button-row"):
            yield Button("Attach", id="btn-attach", variant="primary")
            yield Button("Cancel", id="btn-cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-attach":
            app_input = self.query_one("#app-name-input", Input)
            app_name = app_input.value.strip()

            if not app_name:
                self.app.notify("App name is required", severity="error")
                return

            self.post_message(AddonAttached(self.addon_name, app_name))
        else:
            self.post_message(AddonDialogCancelled())


class AddonCreated(Message):
    """Message posted when an addon is created."""

    def __init__(self, addon_type: str, addon_name: str) -> None:
        super().__init__()
        self.addon_type = addon_type
        self.addon_name = addon_name


class AddonAttached(Message):
    """Message posted when an addon is attached."""

    def __init__(self, addon_name: str, app_name: str) -> None:
        super().__init__()
        self.addon_name = addon_name
        self.app_name = app_name


class AddonDialogCancelled(Message):
    """Message posted when a dialog is cancelled."""


class AddonsScreen(Screen):
    """Screen for viewing and managing addons."""

    CSS = """
    AddonsScreen {
        layout: vertical;
    }

    #addons-header {
        height: 3;
        padding: 0 1;
        background: $primary-darken-2;
    }

    #addons-title {
        text-style: bold;
    }

    #addons-table-container {
        height: 1fr;
        padding: 1;
    }

    #addons-table {
        height: 1fr;
    }

    #addons-actions {
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    .addon-running {
        color: $success;
    }

    .addon-stopped {
        color: $text-muted;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back"),
        Binding("n", "new_addon", "New"),
        Binding("a", "attach_addon", "Attach"),
        Binding("d", "detach_addon", "Detach"),
        Binding("D", "delete_addon", "Delete"),
        Binding("R", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._addons: list[dict[str, Any]] = []
        self._dialog_open: bool = False

    @property
    def hop3_app(self) -> Hop3TUI | None:
        """Get the Hop3TUI app instance if available."""
        if hasattr(self.app, "api_client"):
            return self.app  # type: ignore[return-value]
        return None

    def compose(self) -> ComposeResult:
        yield Header()
        with Static(id="addons-header"):
            yield Static("Addons", id="addons-title")
        with Vertical(id="addons-table-container"):
            yield DataTable(id="addons-table")
        with Horizontal(id="addons-actions"):
            yield Static(
                "[n] New  [a] Attach  [d] Detach  [D] Delete  [R] Refresh  [Esc] Back"
            )
        yield Footer()

    def on_mount(self) -> None:
        """Set up the addons table."""
        table = self.query_one("#addons-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("NAME", "TYPE", "APP", "STATUS")
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Refresh addons from server."""
        self.run_worker(self._fetch_addons(), exclusive=True)

    async def _fetch_addons(self) -> None:
        """Fetch addons from server asynchronously."""
        if not self.hop3_app:
            # No API client available, use mock data
            self._addons = [
                {
                    "name": "mydb",
                    "type": "postgresql",
                    "app_name": "myapp",
                    "status": "running",
                },
                {
                    "name": "cache",
                    "type": "redis",
                    "app_name": "myapp",
                    "status": "running",
                },
                {
                    "name": "api-db",
                    "type": "postgresql",
                    "app_name": "api-server",
                    "status": "running",
                },
                {
                    "name": "unused-redis",
                    "type": "redis",
                    "app_name": None,
                    "status": "stopped",
                },
            ]
            self._update_table()
            return

        try:
            self._addons = await self.hop3_app.api_client.list_addons()
            self._update_table()
        except Exception as e:
            self.notify(f"Failed to fetch addons: {e}", severity="error", timeout=5)

    def _update_table(self) -> None:
        """Update the table with current addons."""
        table = self.query_one("#addons-table", DataTable)
        table.clear()

        for addon in sorted(self._addons, key=lambda a: a.get("name", "")):
            status = addon.get("status", "unknown")
            status_style = "green" if status == "running" else "dim"
            app_name = addon.get("app_name") or "[dim]unattached[/]"

            table.add_row(
                addon["name"],
                addon["type"],
                app_name,
                f"[{status_style}]{status.upper()}[/]",
                key=addon["name"],
            )

    def _get_selected_addon(self) -> dict[str, Any] | None:
        """Get the currently selected addon."""
        table = self.query_one("#addons-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            addon_name = str(table.get_cell_at((table.cursor_row, 0)))
            for addon in self._addons:
                if addon["name"] == addon_name:
                    return addon
        return None

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.app.switch_mode("dashboard")

    def action_new_addon(self) -> None:
        """Create a new addon."""
        if self._dialog_open:
            return
        dialog = CreateAddonDialog()
        self.mount(dialog)
        self._dialog_open = True

    def action_attach_addon(self) -> None:
        """Attach the selected addon to an app."""
        if self._dialog_open:
            return

        addon = self._get_selected_addon()
        if not addon:
            self.notify("No addon selected", severity="warning")
            return

        if addon.get("app_name"):
            self.notify("Addon is already attached", severity="warning")
            return

        dialog = AttachAddonDialog(addon["name"])
        self.mount(dialog)
        self._dialog_open = True

    def action_detach_addon(self) -> None:
        """Detach the selected addon from its app."""
        addon = self._get_selected_addon()
        if not addon:
            self.notify("No addon selected", severity="warning")
            return

        if not addon.get("app_name"):
            self.notify("Addon is not attached to any app", severity="warning")
            return

        # Confirm detach
        dialog = ConfirmationDialog(
            title="Detach Addon",
            message=f"Detach {addon['name']} from {addon['app_name']}?",
            confirm_label="Detach",
            cancel_label="Cancel",
        )
        self.mount(dialog)
        self._pending_action = ("detach", addon)

    def action_delete_addon(self) -> None:
        """Delete the selected addon."""
        addon = self._get_selected_addon()
        if not addon:
            self.notify("No addon selected", severity="warning")
            return

        if addon.get("app_name"):
            self.notify("Cannot delete attached addon. Detach first.", severity="error")
            return

        dialog = ConfirmationDialog(
            title="Delete Addon",
            message=f"Are you sure you want to delete {addon['name']}?\nThis cannot be undone.",
            confirm_label="Delete",
            cancel_label="Cancel",
        )
        self.mount(dialog)
        self._pending_action = ("delete", addon)

    def action_refresh(self) -> None:
        """Refresh the addons list."""
        self._refresh_data()
        self.notify("Refreshing addons...")

    def on_addon_created(self, event: AddonCreated) -> None:
        """Handle addon creation."""
        self._close_dialog(CreateAddonDialog)
        self.run_worker(self._create_addon(event.addon_type, event.addon_name))

    async def _create_addon(self, addon_type: str, addon_name: str) -> None:
        """Create an addon."""
        if not self.hop3_app:
            # Mock create
            self._addons.append({
                "name": addon_name,
                "type": addon_type,
                "app_name": None,
                "status": "running",
            })
            self._update_table()
            self.notify(f"[green]Created {addon_name}[/]")
            return

        try:
            await self.hop3_app.api_client.create_addon(addon_type, addon_name)
            self.notify(f"[green]Created {addon_name}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to create addon: {e}", severity="error")

    def on_addon_attached(self, event: AddonAttached) -> None:
        """Handle addon attach."""
        self._close_dialog(AttachAddonDialog)
        self.run_worker(self._attach_addon(event.addon_name, event.app_name))

    async def _attach_addon(self, addon_name: str, app_name: str) -> None:
        """Attach an addon to an app."""
        if not self.hop3_app:
            # Mock attach
            for addon in self._addons:
                if addon["name"] == addon_name:
                    addon["app_name"] = app_name
                    break
            self._update_table()
            self.notify(f"[green]Attached {addon_name} to {app_name}[/]")
            return

        try:
            await self.hop3_app.api_client.attach_addon(addon_name, app_name)
            self.notify(f"[green]Attached {addon_name} to {app_name}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to attach addon: {e}", severity="error")

    def on_addon_dialog_cancelled(self, event: AddonDialogCancelled) -> None:
        """Handle dialog cancellation."""
        self._close_dialog(CreateAddonDialog)
        self._close_dialog(AttachAddonDialog)

    def on_confirmation_dialog_confirmed(
        self, event: ConfirmationDialog.Confirmed
    ) -> None:
        """Handle confirmation."""
        self._close_dialog(ConfirmationDialog)

        if hasattr(self, "_pending_action"):
            action, addon = self._pending_action
            if action == "detach":
                self.run_worker(self._detach_addon(addon["name"], addon["app_name"]))
            elif action == "delete":
                self.run_worker(self._delete_addon(addon["name"]))
            del self._pending_action

    def on_confirmation_dialog_cancelled(
        self, event: ConfirmationDialog.Cancelled
    ) -> None:
        """Handle confirmation cancellation."""
        self._close_dialog(ConfirmationDialog)
        if hasattr(self, "_pending_action"):
            del self._pending_action

    async def _detach_addon(self, addon_name: str, app_name: str) -> None:
        """Detach an addon from an app."""
        if not self.hop3_app:
            # Mock detach
            for addon in self._addons:
                if addon["name"] == addon_name:
                    addon["app_name"] = None
                    addon["status"] = "stopped"
                    break
            self._update_table()
            self.notify(f"[yellow]Detached {addon_name}[/]")
            return

        try:
            await self.hop3_app.api_client.detach_addon(addon_name, app_name)
            self.notify(f"[yellow]Detached {addon_name}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to detach addon: {e}", severity="error")

    async def _delete_addon(self, addon_name: str) -> None:
        """Delete an addon."""
        if not self.hop3_app:
            # Mock delete
            self._addons = [a for a in self._addons if a["name"] != addon_name]
            self._update_table()
            self.notify(f"[red]Deleted {addon_name}[/]")
            return

        try:
            await self.hop3_app.api_client.delete_addon(addon_name)
            self.notify(f"[red]Deleted {addon_name}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to delete addon: {e}", severity="error")

    def _close_dialog(self, dialog_type: type) -> None:
        """Close dialogs of a given type."""
        dialogs = self.query(dialog_type)
        for dialog in dialogs:
            dialog.remove()
        self._dialog_open = False
