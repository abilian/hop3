# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Main Hop3 TUI Application."""

from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from hop3_tui.screens.apps import AppsScreen
from hop3_tui.screens.chat import ChatScreen
from hop3_tui.screens.dashboard import DashboardScreen
from hop3_tui.screens.system import SystemScreen


class Hop3TUI(App[str]):
    """Hop3 Terminal User Interface Application."""

    TITLE = "Hop3"
    SUB_TITLE = "Platform as a Service"

    CSS_PATH = "styles/base.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
        Binding("d", "switch_mode('dashboard')", "Dashboard", show=True),
        Binding("a", "switch_mode('apps')", "Apps", show=True),
        Binding("s", "switch_mode('system')", "System", show=True),
        Binding("c", "switch_mode('chat')", "Chat", show=True),
    ]

    MODES = {
        "dashboard": DashboardScreen,
        "apps": AppsScreen,
        "system": SystemScreen,
        "chat": ChatScreen,
    }

    def __init__(self) -> None:
        super().__init__()
        self.dark = True

    def on_mount(self) -> None:
        """Set up the application on mount."""
        self.switch_mode("dashboard")

    def action_help(self) -> None:
        """Show help overlay."""
        self.notify("Help: Press ? for help, q to quit", title="Hop3 TUI")
