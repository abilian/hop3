# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""System status screen."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from hop3_tui.screens.processes import ProcessesScreen
from hop3_tui.screens.system_logs import SystemLogsScreen


class ResourcesPanel(Static):
    """Panel showing system resources."""

    cpu: reactive[float] = reactive(0.0)
    memory: reactive[float] = reactive(0.0)
    disk: reactive[float] = reactive(0.0)

    def compose(self) -> ComposeResult:
        yield Static("RESOURCES", classes="panel-title")
        yield Static(id="resources-content")

    def on_mount(self) -> None:
        self._update_display()

    def watch_cpu(self, value: float) -> None:
        self._update_display()

    def watch_memory(self, value: float) -> None:
        self._update_display()

    def watch_disk(self, value: float) -> None:
        self._update_display()

    def _update_display(self) -> None:
        content = self.query_one("#resources-content", Static)
        content.update(
            f"CPU:    {self._make_bar(self.cpu)} {self.cpu:.0f}%\n"
            f"Memory: {self._make_bar(self.memory)} {self.memory:.0f}%\n"
            f"Disk:   {self._make_bar(self.disk)} {self.disk:.0f}%"
        )

    def _make_bar(self, percent: float, width: int = 10) -> str:
        """Create a progress bar string."""
        filled = int(percent / 100 * width)
        empty = width - filled

        # Color based on percentage
        if percent >= 90:
            color = "red"
        elif percent >= 70:
            color = "yellow"
        else:
            color = "green"

        return f"[{color}]{'█' * filled}[/][dim]{'░' * empty}[/]"


class ServicesPanel(Static):
    """Panel showing service status."""

    def compose(self) -> ComposeResult:
        yield Static("SERVICES", classes="panel-title")
        yield Static(id="services-content")

    def on_mount(self) -> None:
        self._update_display()

    def update_services(self, services: dict[str, bool]) -> None:
        """Update services status."""
        self._services = services
        self._update_display()

    def _update_display(self) -> None:
        content = self.query_one("#services-content", Static)
        # Default services
        services = {
            "nginx": True,
            "supervisor": True,
            "postgresql": True,
            "redis": True,
        }

        lines = []
        for name, running in services.items():
            status = "[green]RUNNING[/]" if running else "[red]STOPPED[/]"
            lines.append(f"{name:<12} {status}")

        content.update("\n".join(lines))


class SystemInfoPanel(Static):
    """Panel showing system information."""

    def compose(self) -> ComposeResult:
        yield Static("INFO", classes="panel-title")
        yield Static(id="info-content")

    def on_mount(self) -> None:
        self._update_display()

    def update_info(
        self,
        hostname: str = "unknown",
        version: str = "unknown",
        uptime: str = "unknown",
    ) -> None:
        content = self.query_one("#info-content", Static)
        content.update(f"Hostname: {hostname}\nHop3:     {version}\nUptime:   {uptime}")

    def _update_display(self) -> None:
        self.update_info("hop3.dev", "v0.5.0", "14d 3h 22m")


class SystemScreen(Screen):
    """Screen showing system status and information."""

    CSS = """
    SystemScreen {
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
        padding: 1;
    }

    .panel {
        border: solid $primary;
        padding: 1;
    }

    .panel-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #resources-panel {
        row-span: 1;
    }

    #services-panel {
        row-span: 1;
    }

    #info-panel {
        column-span: 2;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "switch_mode('dashboard')", "Back"),
        Binding("l", "view_system_logs", "Logs"),
        Binding("p", "view_processes", "Processes"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="resources-panel", classes="panel"):
            yield ResourcesPanel()
        with Container(id="services-panel", classes="panel"):
            yield ServicesPanel()
        with Container(id="info-panel", classes="panel"):
            yield SystemInfoPanel()
        yield Footer()

    def on_mount(self) -> None:
        """Initialize system data."""
        self.set_interval(5, self._refresh_data)
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Refresh system data from server."""
        # TODO: Fetch from API
        resources = self.query_one(ResourcesPanel)
        resources.cpu = 42.0
        resources.memory = 63.0
        resources.disk = 81.0

    def action_view_system_logs(self) -> None:
        """View system logs."""
        self.app.push_screen(SystemLogsScreen())

    def action_view_processes(self) -> None:
        """View running processes."""
        self.app.push_screen(ProcessesScreen())

    def action_refresh(self) -> None:
        """Refresh system data."""
        self._refresh_data()
        self.notify("System status refreshed")
