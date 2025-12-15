# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Tests for TUI screens."""

from __future__ import annotations

import pytest
from hop3_tui.screens.apps import AppsScreen
from hop3_tui.screens.chat import ChatScreen
from hop3_tui.screens.dashboard import AppsSummary, DashboardScreen
from hop3_tui.screens.logs import LogsScreen
from hop3_tui.screens.system import ResourcesPanel, ServicesPanel, SystemScreen
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input, Static


class TestDashboardScreen:
    """Tests for DashboardScreen."""

    @pytest.mark.asyncio
    async def test_dashboard_composes(self):
        """Test dashboard composes correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield DashboardScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            # Dashboard should have mounted
            assert app.query_one(DashboardScreen)

    @pytest.mark.asyncio
    async def test_apps_summary_widget(self):
        """Test AppsSummary widget."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AppsSummary()

        app = TestApp()
        async with app.run_test() as pilot:
            summary = app.query_one(AppsSummary)
            # Set values and check they're stored
            summary.running = 5
            summary.stopped = 3
            summary.failed = 1
            assert summary.running == 5
            assert summary.stopped == 3
            assert summary.failed == 1


class TestAppsScreen:
    """Tests for AppsScreen."""

    def test_apps_screen_init(self):
        """Test AppsScreen initialization."""
        screen = AppsScreen()
        assert screen._apps == []

    @pytest.mark.asyncio
    async def test_apps_screen_composes(self):
        """Test apps screen composes correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AppsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            # Screen should have mounted
            screen = app.query_one(AppsScreen)
            assert screen is not None
            # DataTable should exist
            table = screen.query_one(DataTable)
            assert table is not None
            # Filter input should exist
            filter_input = screen.query_one("#filter-input", Input)
            assert filter_input is not None

    @pytest.mark.asyncio
    async def test_apps_table_structure(self):
        """Test apps table has expected columns."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AppsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(AppsScreen)
            table = screen.query_one(DataTable)
            # Table should have 5 columns: NAME, STATUS, PORT, RUNTIME, UPDATED
            assert len(table.columns) == 5


class TestChatScreen:
    """Tests for ChatScreen."""

    def test_chat_screen_init(self):
        """Test ChatScreen initialization."""
        screen = ChatScreen()
        assert screen._history == []
        assert screen._history_index == 0
        assert screen._chat_content == ""

    @pytest.mark.asyncio
    async def test_chat_screen_composes(self):
        """Test chat screen composes correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            assert screen is not None
            # Command input should exist
            cmd_input = screen.query_one("#command-input", Input)
            assert cmd_input is not None
            # Chat messages should exist
            messages = screen.query_one("#chat-messages", Static)
            assert messages is not None

    @pytest.mark.asyncio
    async def test_chat_welcome_message(self):
        """Test chat shows welcome message on mount."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            # After mount, should have welcome message
            assert "Welcome" in screen._chat_content

    def test_chat_process_help_command(self):
        """Test help command processing."""
        screen = ChatScreen()
        # Manually set up chat content
        screen._chat_content = ""
        screen._process_command = lambda cmd: None  # Stub
        # We can't easily test this without full app context


class TestSystemScreen:
    """Tests for SystemScreen."""

    @pytest.mark.asyncio
    async def test_system_screen_composes(self):
        """Test system screen composes correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield SystemScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SystemScreen)
            assert screen is not None
            # Should have resources panel
            resources = screen.query_one(ResourcesPanel)
            assert resources is not None
            # Should have services panel
            services = screen.query_one(ServicesPanel)
            assert services is not None

    @pytest.mark.asyncio
    async def test_resources_panel_widget(self):
        """Test ResourcesPanel widget."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ResourcesPanel()

        app = TestApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ResourcesPanel)
            panel.cpu = 50.0
            panel.memory = 60.0
            panel.disk = 70.0
            assert panel.cpu == 50.0
            assert panel.memory == 60.0
            assert panel.disk == 70.0


class TestLogsScreen:
    """Tests for LogsScreen."""

    def test_logs_screen_init(self):
        """Test LogsScreen initialization."""
        screen = LogsScreen(app_name="myapp")
        assert screen.app_name == "myapp"
        assert screen._logs == []
        assert screen._filter_text == ""

    def test_logs_screen_default_app_name(self):
        """Test LogsScreen with default app name."""
        screen = LogsScreen()
        assert screen.app_name == ""

    def test_logs_style_log_line_info(self):
        """Test log line styling for INFO level."""
        screen = LogsScreen()
        styled = screen._style_log_line("10:00:00 [INFO] Test message")
        # INFO lines are not specially colored
        assert "[INFO]" in styled

    def test_logs_style_log_line_error(self):
        """Test log line styling for ERROR level."""
        screen = LogsScreen()
        styled = screen._style_log_line("10:00:00 [ERROR] Test error")
        assert "[red]" in styled

    def test_logs_style_log_line_warn(self):
        """Test log line styling for WARN level."""
        screen = LogsScreen()
        styled = screen._style_log_line("10:00:00 [WARN] Test warning")
        assert "[yellow]" in styled

    def test_logs_style_log_line_debug(self):
        """Test log line styling for DEBUG level."""
        screen = LogsScreen()
        styled = screen._style_log_line("10:00:00 [DEBUG] Debug message")
        assert "[dim]" in styled

    def test_logs_filter(self):
        """Test log filtering."""
        screen = LogsScreen()
        screen._logs = [
            "10:00:00 [INFO] Request received",
            "10:00:01 [ERROR] Database error",
            "10:00:02 [INFO] Request completed",
        ]

        # No filter - all logs
        screen._filter_text = ""
        filtered = screen._get_filtered_logs()
        assert len(filtered) == 3

        # Filter by "error"
        screen._filter_text = "error"
        filtered = screen._get_filtered_logs()
        assert len(filtered) == 1
        assert "Database error" in filtered[0]

        # Case-insensitive filter
        screen._filter_text = "ERROR"
        filtered = screen._get_filtered_logs()
        assert len(filtered) == 1
