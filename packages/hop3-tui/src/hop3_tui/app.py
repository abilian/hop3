# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Main Hop3 TUI Application."""

from __future__ import annotations

from typing import ClassVar

from textual.app import App
from textual.binding import Binding

from hop3_tui.api.client import Hop3Client
from hop3_tui.config import TUIConfig, get_config
from hop3_tui.screens.addons import AddonsScreen
from hop3_tui.screens.app_detail import AppDetailScreen
from hop3_tui.screens.apps import AppsScreen
from hop3_tui.screens.backups import BackupsScreen
from hop3_tui.screens.chat import ChatScreen
from hop3_tui.screens.dashboard import DashboardScreen
from hop3_tui.screens.env_vars import EnvVarsScreen
from hop3_tui.screens.logs import LogsScreen
from hop3_tui.screens.system import SystemScreen


class Hop3TUI(App[str]):
    """Hop3 Terminal User Interface Application."""

    TITLE = "Hop3"
    SUB_TITLE = "Platform as a Service"

    CSS_PATH = "styles/base.tcss"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
        Binding("d", "switch_mode('dashboard')", "Dashboard", show=True),
        Binding("a", "switch_mode('apps')", "Apps", show=True),
        Binding("s", "switch_mode('system')", "System", show=True),
        Binding("o", "switch_mode('addons')", "Addons", show=True),
        Binding("b", "switch_mode('backups')", "Backups", show=True),
        Binding("c", "switch_mode('chat')", "Chat", show=True),
    ]

    MODES: ClassVar[dict[str, type]] = {
        "dashboard": DashboardScreen,
        "apps": AppsScreen,
        "system": SystemScreen,
        "addons": AddonsScreen,
        "backups": BackupsScreen,
        "chat": ChatScreen,
    }

    # Screens that can be pushed onto the stack
    SCREENS: ClassVar[dict[str, type]] = {
        "app_detail": AppDetailScreen,
        "logs": LogsScreen,
    }

    def __init__(self, config: TUIConfig | None = None) -> None:
        super().__init__()
        self.config = config or get_config()
        self.api_client = Hop3Client(
            base_url=self.config.server_url,
            token=self.config.auth_token,
        )
        self.dark = self.config.theme == "dark"

    def on_mount(self) -> None:
        """Set up the application on mount."""
        self.switch_mode("dashboard")
        # Show connection info
        self.notify(
            f"Connected to {self.config.server_url}",
            title="Hop3 TUI",
            timeout=3,
        )

    def action_help(self) -> None:
        """Show help overlay."""
        self.notify(
            "Navigation: d=Dashboard, a=Apps, s=System, o=Addons, b=Backups, c=Chat\n"
            "Actions: q=Quit, ?=Help",
            title="Hop3 TUI Help",
            timeout=5,
        )

    def push_app_detail(self, app_name: str) -> None:
        """Push the app detail screen for a specific app."""
        self.push_screen(AppDetailScreen(app_name=app_name))

    def push_logs(self, app_name: str) -> None:
        """Push the logs screen for a specific app."""
        self.push_screen(LogsScreen(app_name=app_name))

    def push_env_vars(self, app_name: str) -> None:
        """Push the env vars screen for a specific app."""
        self.push_screen(EnvVarsScreen(app_name=app_name))
