# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Processes viewing screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

if TYPE_CHECKING:
    from hop3_tui.app import Hop3TUI


class ProcessesScreen(Screen):
    """Screen for viewing running processes."""

    CSS = """
    ProcessesScreen {
        layout: vertical;
    }

    #processes-header {
        height: 3;
        padding: 0 1;
        background: $primary-darken-2;
    }

    #processes-title {
        text-style: bold;
    }

    #processes-table {
        height: 1fr;
    }

    #processes-footer {
        height: 3;
        padding: 0 1;
        background: $surface;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("k", "kill_process", "Kill"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._processes: list[dict[str, Any]] = []

    @property
    def hop3_app(self) -> Hop3TUI | None:
        """Get the Hop3TUI app instance if available."""
        if hasattr(self.app, "api_client"):
            return self.app  # type: ignore[return-value]
        return None

    def compose(self) -> ComposeResult:
        yield Header()
        with Static(id="processes-header"):
            yield Static("Running Processes", id="processes-title")
        yield DataTable(id="processes-table")
        with Static(id="processes-footer"):
            yield Static("[r] Refresh  [k] Kill  [Esc] Back")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the processes table."""
        table = self.query_one("#processes-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("NAME", "PID", "STATUS", "CPU %", "MEM %", "UPTIME")
        self._refresh_data()
        self.set_interval(5, self._refresh_data)

    def _refresh_data(self) -> None:
        """Refresh processes from server."""
        self.run_worker(self._fetch_processes(), exclusive=True)

    async def _fetch_processes(self) -> None:
        """Fetch processes from server asynchronously."""
        if not self.hop3_app:
            # Mock data for testing
            self._processes = [
                {
                    "name": "nginx",
                    "pid": 1234,
                    "status": "running",
                    "cpu": 2.5,
                    "memory": 1.2,
                    "uptime": "14d 3h",
                },
                {
                    "name": "supervisord",
                    "pid": 1235,
                    "status": "running",
                    "cpu": 0.1,
                    "memory": 0.5,
                    "uptime": "14d 3h",
                },
                {
                    "name": "postgresql",
                    "pid": 1240,
                    "status": "running",
                    "cpu": 5.2,
                    "memory": 8.3,
                    "uptime": "14d 3h",
                },
                {
                    "name": "redis-server",
                    "pid": 1245,
                    "status": "running",
                    "cpu": 1.0,
                    "memory": 2.1,
                    "uptime": "14d 3h",
                },
                {
                    "name": "myapp:web",
                    "pid": 2001,
                    "status": "running",
                    "cpu": 15.3,
                    "memory": 12.5,
                    "uptime": "2d 5h",
                },
                {
                    "name": "myapp:worker",
                    "pid": 2002,
                    "status": "running",
                    "cpu": 8.7,
                    "memory": 6.2,
                    "uptime": "2d 5h",
                },
                {
                    "name": "api-server:web",
                    "pid": 2010,
                    "status": "running",
                    "cpu": 12.1,
                    "memory": 9.8,
                    "uptime": "5d 12h",
                },
            ]
            self._update_table()
            return

        try:
            self._processes = await self.hop3_app.api_client.get_processes()
            self._update_table()
        except Exception as e:
            self.notify(f"Failed to fetch processes: {e}", severity="error", timeout=5)

    def _update_table(self) -> None:
        """Update the table with current processes."""
        table = self.query_one("#processes-table", DataTable)
        table.clear()

        for proc in sorted(self._processes, key=lambda p: p.get("name", "")):
            status = proc.get("status", "unknown")
            status_style = "green" if status == "running" else "red"
            cpu = proc.get("cpu", 0)
            memory = proc.get("memory", 0)

            # Color CPU/memory based on usage
            cpu_style = "red" if cpu > 50 else ("yellow" if cpu > 25 else "green")
            mem_style = "red" if memory > 50 else ("yellow" if memory > 25 else "green")

            table.add_row(
                proc.get("name", ""),
                str(proc.get("pid", "")),
                f"[{status_style}]{status.upper()}[/]",
                f"[{cpu_style}]{cpu:.1f}%[/]",
                f"[{mem_style}]{memory:.1f}%[/]",
                proc.get("uptime", ""),
                key=str(proc.get("pid", "")),
            )

    def _get_selected_process(self) -> dict[str, Any] | None:
        """Get the currently selected process."""
        table = self.query_one("#processes-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            pid = str(table.get_cell_at((table.cursor_row, 1)))
            for proc in self._processes:
                if str(proc.get("pid", "")) == pid:
                    return proc
        return None

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.app.pop_screen()

    def action_refresh(self) -> None:
        """Refresh the processes list."""
        self._refresh_data()
        self.notify("Refreshing processes...")

    def action_kill_process(self) -> None:
        """Kill the selected process."""
        proc = self._get_selected_process()
        if not proc:
            self.notify("No process selected", severity="warning")
            return

        name = proc.get("name", "unknown")
        # Don't allow killing system services
        system_services = ["nginx", "supervisord", "postgresql", "redis-server"]
        if name in system_services:
            self.notify(
                f"Cannot kill system service: {name}",
                severity="error",
            )
            return

        self.notify(f"[yellow]Kill process not yet implemented: {name}[/]")
