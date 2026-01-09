# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Confirmation dialog widget."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmationDialog(ModalScreen[bool]):
    """A modal dialog for confirming destructive actions."""

    DEFAULT_CSS = """
    ConfirmationDialog {
        align: center middle;
    }

    #dialog {
        width: 50;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #dialog-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #dialog-message {
        margin-bottom: 1;
    }

    #dialog-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #dialog-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        on_confirm: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.message = message
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label
        self.on_confirm = on_confirm

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.title_text, id="dialog-title")
            yield Static(self.message, id="dialog-message")
            with Horizontal(id="dialog-buttons"):
                yield Button(self.confirm_label, id="btn-confirm", variant="error")
                yield Button(self.cancel_label, id="btn-cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-confirm":
            if self.on_confirm:
                self.on_confirm()
            self.dismiss(True)  # noqa: FBT003
        else:
            self.dismiss(False)  # noqa: FBT003

    def on_key(self, event) -> None:
        """Handle key presses."""
        if event.key == "escape":
            self.dismiss(False)  # noqa: FBT003
        elif event.key == "enter":
            # Don't auto-confirm, require explicit button press
            pass
