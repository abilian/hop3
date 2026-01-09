# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Environment variables management screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from hop3_tui.api.models import EnvVar
from hop3_tui.widgets.confirmation import ConfirmationDialog

if TYPE_CHECKING:
    from hop3_tui.app import Hop3TUI


class EnvVarEditDialog(Static):
    """Dialog for adding/editing environment variables."""

    DEFAULT_CSS = """
    EnvVarEditDialog {
        align: center middle;
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: solid $primary;
    }

    EnvVarEditDialog #dialog-title {
        text-style: bold;
        margin-bottom: 1;
    }

    EnvVarEditDialog .field-label {
        margin-top: 1;
    }

    EnvVarEditDialog Input {
        margin-bottom: 1;
    }

    EnvVarEditDialog #button-row {
        margin-top: 1;
        align: center middle;
    }

    EnvVarEditDialog Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        app_name: str,
        var_name: str = "",
        var_value: str = "",
        *,
        is_edit: bool = False,
    ) -> None:
        super().__init__()
        self.app_name = app_name
        self.var_name = var_name
        self.var_value = var_value
        self.is_edit = is_edit

    def compose(self) -> ComposeResult:
        title = "Edit Variable" if self.is_edit else "Add Variable"
        yield Static(title, id="dialog-title")
        yield Label("Name:", classes="field-label")
        yield Input(
            value=self.var_name,
            placeholder="VARIABLE_NAME",
            id="var-name-input",
            disabled=self.is_edit,
        )
        yield Label("Value:", classes="field-label")
        yield Input(
            value=self.var_value,
            placeholder="variable_value",
            id="var-value-input",
            password=False,
        )
        with Horizontal(id="button-row"):
            yield Button("Save", id="btn-save", variant="primary")
            yield Button("Cancel", id="btn-cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            name_input = self.query_one("#var-name-input", Input)
            value_input = self.query_one("#var-value-input", Input)
            name = name_input.value.strip()
            value = value_input.value

            if not name:
                self.app.notify("Variable name is required", severity="error")
                return

            # Post message to parent screen
            self.post_message(EnvVarSaved(self.app_name, name, value))
        else:
            self.post_message(EnvVarEditCancelled())


class EnvVarSaved(Message):
    """Message posted when an env var is saved."""

    def __init__(self, app_name: str, name: str, value: str) -> None:
        super().__init__()
        self.app_name = app_name
        self.var_name = name
        self.var_value = value


class EnvVarEditCancelled(Message):
    """Message posted when edit is cancelled."""


class EnvVarsScreen(Screen):
    """Screen for viewing and managing environment variables."""

    CSS = """
    EnvVarsScreen {
        layout: vertical;
    }

    #env-header {
        height: 3;
        padding: 0 1;
        background: $primary-darken-2;
    }

    #env-title {
        text-style: bold;
    }

    #env-table-container {
        height: 1fr;
        padding: 1;
    }

    #env-table {
        height: 1fr;
    }

    #env-actions {
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    .service-var {
        color: $text-muted;
    }

    .hidden-value {
        color: $warning;
    }

    #dialog-overlay {
        align: center middle;
        background: $background 80%;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back"),
        Binding("a", "add_var", "Add"),
        Binding("e", "edit_var", "Edit"),
        Binding("d", "delete_var", "Delete"),
        Binding("t", "toggle_visibility", "Toggle Hidden"),
        Binding("R", "refresh", "Refresh"),
    ]

    def __init__(self, app_name: str = "") -> None:
        super().__init__()
        self.app_name = app_name
        self._env_vars: list[EnvVar] = []
        self._show_hidden: bool = False
        self._editing: bool = False

    @property
    def hop3_app(self) -> Hop3TUI | None:
        """Get the Hop3TUI app instance if available."""
        if hasattr(self.app, "api_client"):
            return self.app  # type: ignore[return-value]
        return None

    def compose(self) -> ComposeResult:
        yield Header()
        with Static(id="env-header"):
            yield Static(f"Environment Variables: {self.app_name}", id="env-title")
        with Vertical(id="env-table-container"):
            yield DataTable(id="env-table")
        with Horizontal(id="env-actions"):
            yield Static(
                "[a] Add  [e] Edit  [d] Delete  [t] Toggle Hidden  [R] Refresh  [Esc] Back"
            )
        yield Footer()

    def on_mount(self) -> None:
        """Set up the env vars table."""
        table = self.query_one("#env-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("NAME", "VALUE", "TYPE")
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Refresh env vars from server."""
        self.run_worker(self._fetch_env_vars(), exclusive=True)

    async def _fetch_env_vars(self) -> None:
        """Fetch env vars from server asynchronously."""
        if not self.hop3_app:
            # No API client available, use mock data
            self._env_vars = [
                EnvVar(name="DEBUG", value="false", is_service_var=False),
                EnvVar(
                    name="API_KEY", value="sk-secret-key-12345", is_service_var=False
                ),
                EnvVar(name="MAX_WORKERS", value="4", is_service_var=False),
                EnvVar(
                    name="DATABASE_URL",
                    value="postgres://localhost/myapp",
                    is_service_var=True,
                ),
                EnvVar(
                    name="REDIS_URL",
                    value="redis://localhost:6379",
                    is_service_var=True,
                ),
            ]
            self._update_table()
            return

        try:
            self._env_vars = await self.hop3_app.api_client.get_env_vars(self.app_name)
            self._update_table()
        except Exception as e:
            self.notify(f"Failed to fetch env vars: {e}", severity="error", timeout=5)

    def _update_table(self) -> None:
        """Update the table with current env vars."""
        table = self.query_one("#env-table", DataTable)
        table.clear()

        # Sort: user vars first, then service vars, alphabetically within each group
        user_vars = sorted(
            [v for v in self._env_vars if not v.is_service_var],
            key=lambda v: v.name,
        )
        service_vars = sorted(
            [v for v in self._env_vars if v.is_service_var],
            key=lambda v: v.name,
        )

        for var in user_vars:
            display_value = self._format_value(var.value)
            table.add_row(var.name, display_value, "user", key=var.name)

        for var in service_vars:
            display_value = self._format_value(var.value)
            table.add_row(
                f"[dim]{var.name}[/]",
                f"[dim]{display_value}[/]",
                "[dim]service[/]",
                key=var.name,
            )

    def _format_value(self, value: str) -> str:
        """Format a value for display, potentially hiding sensitive data."""
        if not self._show_hidden and self._is_sensitive(value):
            return "****hidden****"
        # Truncate long values
        if len(value) > 50:
            return value[:47] + "..."
        return value

    def _is_sensitive(self, value: str) -> bool:
        """Check if a value appears to be sensitive."""
        sensitive_patterns = [
            "sk-",
            "key",
            "secret",
            "password",
            "token",
            "auth",
            "credential",
        ]
        value_lower = value.lower()
        return any(pattern in value_lower for pattern in sensitive_patterns)

    def _get_selected_var(self) -> EnvVar | None:
        """Get the currently selected env var."""
        table = self.query_one("#env-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            var_name = str(table.get_cell_at((table.cursor_row, 0)))
            # Remove dim formatting if present
            var_name = var_name.replace("[dim]", "").replace("[/]", "")
            for var in self._env_vars:
                if var.name == var_name:
                    return var
        return None

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.app.pop_screen()

    def action_add_var(self) -> None:
        """Add a new environment variable."""
        dialog = EnvVarEditDialog(self.app_name, is_edit=False)
        self.mount(dialog)
        self._editing = True

    def action_edit_var(self) -> None:
        """Edit the selected environment variable."""
        var = self._get_selected_var()
        if not var:
            self.notify("No variable selected", severity="warning")
            return

        if var.is_service_var:
            self.notify("Cannot edit service variables", severity="warning")
            return

        dialog = EnvVarEditDialog(
            self.app_name,
            var_name=var.name,
            var_value=var.value,
            is_edit=True,
        )
        self.mount(dialog)
        self._editing = True

    def action_delete_var(self) -> None:
        """Delete the selected environment variable."""
        var = self._get_selected_var()
        if not var:
            self.notify("No variable selected", severity="warning")
            return

        if var.is_service_var:
            self.notify("Cannot delete service variables", severity="warning")
            return

        # Show confirmation dialog
        dialog = ConfirmationDialog(
            title="Delete Variable",
            message=f"Are you sure you want to delete {var.name}?",
            confirm_label="Delete",
            cancel_label="Cancel",
        )
        self.mount(dialog)

    def action_toggle_visibility(self) -> None:
        """Toggle visibility of hidden values."""
        self._show_hidden = not self._show_hidden
        self._update_table()
        if self._show_hidden:
            self.notify("Showing all values")
        else:
            self.notify("Hiding sensitive values")

    def action_refresh(self) -> None:
        """Refresh the env vars list."""
        self._refresh_data()
        self.notify("Refreshing environment variables...")

    def on_env_var_saved(self, event: EnvVarSaved) -> None:
        """Handle env var save."""
        # Remove the dialog
        dialogs = self.query(EnvVarEditDialog)
        for dialog in dialogs:
            dialog.remove()
        self._editing = False

        # Save the variable
        self.run_worker(self._save_env_var(event.var_name, event.var_value))

    async def _save_env_var(self, name: str, value: str) -> None:
        """Save an environment variable."""
        if not self.hop3_app:
            # Mock save
            existing = next((v for v in self._env_vars if v.name == name), None)
            if existing:
                existing.value = value
            else:
                self._env_vars.append(
                    EnvVar(name=name, value=value, is_service_var=False)
                )
            self._update_table()
            self.notify(f"[green]Saved {name}[/]")
            return

        try:
            await self.hop3_app.api_client.set_env_var(self.app_name, name, value)
            self.notify(f"[green]Saved {name}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to save {name}: {e}", severity="error")

    def on_env_var_edit_cancelled(self, event: EnvVarEditCancelled) -> None:
        """Handle edit cancellation."""
        dialogs = self.query(EnvVarEditDialog)
        for dialog in dialogs:
            dialog.remove()
        self._editing = False

    def on_confirmation_dialog_confirmed(
        self, event: ConfirmationDialog.Confirmed
    ) -> None:
        """Handle deletion confirmation."""
        dialogs = self.query(ConfirmationDialog)
        for dialog in dialogs:
            dialog.remove()

        var = self._get_selected_var()
        if var:
            self.run_worker(self._delete_env_var(var.name))

    def on_confirmation_dialog_cancelled(
        self, event: ConfirmationDialog.Cancelled
    ) -> None:
        """Handle deletion cancellation."""
        dialogs = self.query(ConfirmationDialog)
        for dialog in dialogs:
            dialog.remove()

    async def _delete_env_var(self, name: str) -> None:
        """Delete an environment variable."""
        if not self.hop3_app:
            # Mock delete
            self._env_vars = [v for v in self._env_vars if v.name != name]
            self._update_table()
            self.notify(f"[yellow]Deleted {name}[/]")
            return

        try:
            await self.hop3_app.api_client.delete_env_var(self.app_name, name)
            self.notify(f"[yellow]Deleted {name}[/]")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Failed to delete {name}: {e}", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row double-click to edit."""
        if not self._editing:
            self.action_edit_var()
