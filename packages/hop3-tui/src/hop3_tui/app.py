# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Main Hop3 TUI Application."""

from __future__ import annotations

from enum import Enum
from typing import ClassVar

from textual.app import App
from textual.binding import Binding
from textual.reactive import reactive

from hop3_tui.api.client import Hop3Client, Hop3ClientError
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


class ConnectionState(Enum):
    """Connection state to the Hop3 server."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"


class Hop3TUI(App[str]):
    """Hop3 Terminal User Interface Application."""

    TITLE = "Hop3"

    CSS_PATH = "styles/base.tcss"

    BINDINGS: ClassVar = [
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
        Binding("d", "switch_mode('dashboard')", "Dashboard", show=True),
        Binding("a", "switch_mode('apps')", "Apps", show=True),
        Binding("s", "switch_mode('system')", "System", show=True),
        Binding("o", "switch_mode('addons')", "Addons", show=True),
        Binding("b", "switch_mode('backups')", "Backups", show=True),
        Binding("c", "switch_mode('chat')", "Chat", show=True),
    ]

    MODES: ClassVar = {
        "dashboard": DashboardScreen,
        "apps": AppsScreen,
        "system": SystemScreen,
        "addons": AddonsScreen,
        "backups": BackupsScreen,
        "chat": ChatScreen,
    }

    # Screens that can be pushed onto the stack
    SCREENS: ClassVar = {
        "app_detail": AppDetailScreen,
        "logs": LogsScreen,
    }

    # Connection state tracking
    connection_state: reactive[ConnectionState] = reactive(ConnectionState.CONNECTING)
    _consecutive_failures: int = 0
    _max_failures_before_disconnect: int = 3

    def __init__(self, config: TUIConfig | None = None) -> None:
        super().__init__()
        self.config = config or get_config()
        self.api_client = Hop3Client(
            base_url=self.config.server_url,
            token=self.config.auth_token,
        )
        self.dark = self.config.theme == "dark"

    def watch_connection_state(self, state: ConnectionState) -> None:
        """React to connection state changes."""
        # Update subtitle based on connection state
        state_indicators = {
            ConnectionState.CONNECTED: "[green]●[/] Connected",
            ConnectionState.DISCONNECTED: "[red]●[/] Disconnected",
            ConnectionState.CONNECTING: "[yellow]●[/] Connecting...",
        }
        self.sub_title = state_indicators.get(state, "")
        if state == ConnectionState.DISCONNECTED:
            self.notify(
                "Connection lost. Will retry automatically.",
                severity="warning",
                timeout=5,
            )
        elif state == ConnectionState.CONNECTED and self._consecutive_failures > 0:
            self.notify("Connection restored.", severity="information", timeout=3)
            self._consecutive_failures = 0

    def on_mount(self) -> None:
        """Set up the application on mount."""
        self.switch_mode("dashboard")
        # Check connection immediately
        self.run_worker(self._check_connection())
        # Set up periodic health check
        self.set_interval(30, self._periodic_health_check)

    async def _check_connection(self) -> None:
        """Check if server is reachable."""
        self.connection_state = ConnectionState.CONNECTING
        try:
            # Try to list apps as a health check
            await self.api_client.list_apps()
            self.connection_state = ConnectionState.CONNECTED
            self._consecutive_failures = 0
        except Hop3ClientError:
            self._handle_connection_failure()

    def _periodic_health_check(self) -> None:
        """Periodic health check."""
        self.run_worker(self._check_connection())

    def _handle_connection_failure(self) -> None:
        """Handle a connection failure."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._max_failures_before_disconnect:
            self.connection_state = ConnectionState.DISCONNECTED

    def mark_api_success(self) -> None:
        """Mark that an API call succeeded (for screens to call)."""
        if self.connection_state != ConnectionState.CONNECTED:
            self.connection_state = ConnectionState.CONNECTED
        self._consecutive_failures = 0

    def mark_api_failure(self) -> None:
        """Mark that an API call failed (for screens to call)."""
        self._handle_connection_failure()

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
