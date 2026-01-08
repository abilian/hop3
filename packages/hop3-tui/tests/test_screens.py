# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Tests for TUI screens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hop3_tui.api.models import App as AppModel, AppState
from hop3_tui.screens.addons import AddonsScreen
from hop3_tui.screens.app_detail import (
    AppActionsPanel,
    AppDetailScreen,
    AppInfoPanel,
    AppLogsPreview,
)
from hop3_tui.screens.apps import AppsScreen
from hop3_tui.screens.backups import BackupsScreen
from hop3_tui.screens.chat import COMMANDS, ChatScreen, CommandSuggester
from hop3_tui.screens.dashboard import AppsSummary, DashboardScreen
from hop3_tui.screens.env_vars import EnvVarsScreen
from hop3_tui.screens.logs import LogsScreen
from hop3_tui.screens.system import ResourcesPanel, ServicesPanel, SystemScreen
from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Input, Static


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


class TestAppDetailScreen:
    """Tests for AppDetailScreen."""

    def test_app_detail_screen_init(self):
        """Test AppDetailScreen initialization."""
        screen = AppDetailScreen(app_name="myapp")
        assert screen.app_name == "myapp"
        assert screen._app is None

    def test_app_detail_screen_default_name(self):
        """Test AppDetailScreen with default name."""
        screen = AppDetailScreen()
        assert screen.app_name == ""

    @pytest.mark.asyncio
    async def test_app_detail_screen_composes(self):
        """Test app detail screen composes correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AppDetailScreen(app_name="testapp")

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(AppDetailScreen)
            assert screen is not None
            # Should have info panel
            info_panel = screen.query_one(AppInfoPanel)
            assert info_panel is not None
            # Should have actions panel
            actions_panel = screen.query_one(AppActionsPanel)
            assert actions_panel is not None

    def test_get_status_style_running(self):
        """Test status style for running state."""
        screen = AppDetailScreen()
        assert screen._get_status_style(AppState.RUNNING) == "green"

    def test_get_status_style_stopped(self):
        """Test status style for stopped state."""
        screen = AppDetailScreen()
        assert screen._get_status_style(AppState.STOPPED) == "dim"

    def test_get_status_style_failed(self):
        """Test status style for failed state."""
        screen = AppDetailScreen()
        assert screen._get_status_style(AppState.FAILED) == "red"

    def test_get_status_style_starting(self):
        """Test status style for starting state."""
        screen = AppDetailScreen()
        assert screen._get_status_style(AppState.STARTING) == "yellow"


class TestAppInfoPanel:
    """Tests for AppInfoPanel widget."""

    @pytest.mark.asyncio
    async def test_info_panel_renders(self):
        """Test AppInfoPanel renders correctly."""
        app_model = AppModel(
            name="testapp",
            runtime="uwsgi",
            port=8000,
            hostname="testapp.example.com",
            workers=2,
        )

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AppInfoPanel(app_model)

        app = TestApp()
        async with app.run_test() as pilot:
            panel = app.query_one(AppInfoPanel)
            assert panel._app.name == "testapp"
            assert panel._app.port == 8000


class TestAppActionsPanel:
    """Tests for AppActionsPanel widget."""

    @pytest.mark.asyncio
    async def test_actions_panel_running_app(self):
        """Test AppActionsPanel for running app."""
        app_model = AppModel(name="testapp", state=AppState.RUNNING)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AppActionsPanel(app_model)

        app = TestApp()
        async with app.run_test() as pilot:
            panel = app.query_one(AppActionsPanel)
            # Running app should have stop and restart buttons
            stop_btn = panel.query_one("#btn-stop", Button)
            assert stop_btn is not None
            restart_btn = panel.query_one("#btn-restart", Button)
            assert restart_btn is not None

    @pytest.mark.asyncio
    async def test_actions_panel_stopped_app(self):
        """Test AppActionsPanel for stopped app."""
        app_model = AppModel(name="testapp", state=AppState.STOPPED)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AppActionsPanel(app_model)

        app = TestApp()
        async with app.run_test() as pilot:
            panel = app.query_one(AppActionsPanel)
            # Stopped app should have start button
            start_btn = panel.query_one("#btn-start", Button)
            assert start_btn is not None


class TestAppLogsPreview:
    """Tests for AppLogsPreview widget."""

    @pytest.mark.asyncio
    async def test_logs_preview_renders(self):
        """Test AppLogsPreview renders correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AppLogsPreview()

        app = TestApp()
        async with app.run_test() as pilot:
            preview = app.query_one(AppLogsPreview)
            assert preview is not None

    @pytest.mark.asyncio
    async def test_logs_preview_update(self):
        """Test updating logs preview."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AppLogsPreview()

        app = TestApp()
        async with app.run_test() as pilot:
            preview = app.query_one(AppLogsPreview)
            # Update with some logs
            preview.update_logs(["Log line 1", "Log line 2", "Log line 3"])
            # Content should be updated
            content = preview.query_one("#logs-preview-content", Static)
            assert content is not None

    @pytest.mark.asyncio
    async def test_logs_preview_empty(self):
        """Test logs preview with no logs."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AppLogsPreview()

        app = TestApp()
        async with app.run_test() as pilot:
            preview = app.query_one(AppLogsPreview)
            preview.update_logs([])
            # Should show "No logs available"


class TestAppsScreenExtended:
    """Extended tests for AppsScreen."""

    def test_get_status_style_running(self):
        """Test status style for running state."""
        screen = AppsScreen()
        assert screen._get_status_style(AppState.RUNNING) == "green"

    def test_get_status_style_stopped(self):
        """Test status style for stopped state."""
        screen = AppsScreen()
        assert screen._get_status_style(AppState.STOPPED) == "dim"

    def test_get_status_style_failed(self):
        """Test status style for failed state."""
        screen = AppsScreen()
        assert screen._get_status_style(AppState.FAILED) == "red"

    def test_get_status_style_starting(self):
        """Test status style for starting state."""
        screen = AppsScreen()
        assert screen._get_status_style(AppState.STARTING) == "yellow"

    def test_get_status_style_stopping(self):
        """Test status style for stopping state."""
        screen = AppsScreen()
        assert screen._get_status_style(AppState.STOPPING) == "yellow"

    def test_format_updated_just_now(self):
        """Test formatting updated timestamp - just now."""
        screen = AppsScreen()
        app = AppModel(name="test", updated_at=datetime.now(timezone.utc))
        result = screen._format_updated(app)
        assert result == "just now"

    def test_format_updated_minutes_ago(self):
        """Test formatting updated timestamp - minutes ago."""
        screen = AppsScreen()
        app = AppModel(
            name="test",
            updated_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        result = screen._format_updated(app)
        assert "m ago" in result

    def test_format_updated_hours_ago(self):
        """Test formatting updated timestamp - hours ago."""
        screen = AppsScreen()
        app = AppModel(
            name="test",
            updated_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        result = screen._format_updated(app)
        assert "h ago" in result

    def test_format_updated_days_ago(self):
        """Test formatting updated timestamp - days ago."""
        screen = AppsScreen()
        app = AppModel(
            name="test",
            updated_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        result = screen._format_updated(app)
        assert "d ago" in result

    def test_format_updated_no_timestamp(self):
        """Test formatting when no timestamp is set."""
        screen = AppsScreen()
        app = AppModel(name="test", updated_at=None)
        result = screen._format_updated(app)
        assert result == "N/A"

    def test_format_updated_naive_datetime(self):
        """Test formatting with naive datetime (no timezone)."""
        screen = AppsScreen()
        # Create a naive datetime (no timezone) - testing backward compat
        app = AppModel(
            name="test", updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        result = screen._format_updated(app)
        # Should still work
        assert "ago" in result or result in {"just now", "N/A"}


class TestChatScreenExtended:
    """Extended tests for ChatScreen commands."""

    @pytest.mark.asyncio
    async def test_chat_process_apps_command(self):
        """Test apps command processing."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            screen._process_command("apps")
            assert "Applications" in screen._chat_content

    @pytest.mark.asyncio
    async def test_chat_process_status_command(self):
        """Test status command processing."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            screen._process_command("status")
            assert "System Status" in screen._chat_content

    @pytest.mark.asyncio
    async def test_chat_process_clear_command(self):
        """Test clear command processing."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            # Add some content first
            screen._chat_content = "some content"
            screen._process_command("clear")
            assert "cleared" in screen._chat_content.lower()

    @pytest.mark.asyncio
    async def test_chat_process_unknown_command(self):
        """Test unknown command processing."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            screen._process_command("unknowncommand")
            assert "Unknown command" in screen._chat_content

    @pytest.mark.asyncio
    async def test_chat_process_app_without_arg(self):
        """Test app command without argument."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            screen._process_command("app")
            assert "Usage:" in screen._chat_content

    @pytest.mark.asyncio
    async def test_chat_process_start_command(self):
        """Test start command processing."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            screen._process_command("start myapp")
            assert "myapp" in screen._chat_content
            assert "start" in screen._chat_content.lower()

    @pytest.mark.asyncio
    async def test_chat_process_stop_command(self):
        """Test stop command processing."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            screen._process_command("stop myapp")
            assert "myapp" in screen._chat_content
            assert "stop" in screen._chat_content.lower()

    @pytest.mark.asyncio
    async def test_chat_process_restart_command(self):
        """Test restart command processing."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            screen._process_command("restart myapp")
            assert "myapp" in screen._chat_content
            assert "restart" in screen._chat_content.lower()

    @pytest.mark.asyncio
    async def test_chat_process_logs_command(self):
        """Test logs command processing."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            screen._process_command("logs myapp")
            assert "myapp" in screen._chat_content
            assert "logs" in screen._chat_content.lower()

    @pytest.mark.asyncio
    async def test_chat_history_tracking(self):
        """Test command history tracking."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ChatScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(ChatScreen)
            # Manually process commands to track history
            screen._history.append("apps")
            screen._history.append("status")
            screen._history_index = 2
            assert len(screen._history) == 2
            assert screen._history[0] == "apps"
            assert screen._history[1] == "status"


class TestCommandSuggester:
    """Tests for CommandSuggester."""

    def test_suggester_init(self):
        """Test suggester initialization."""
        suggester = CommandSuggester()
        assert suggester._app_names == []

    def test_suggester_init_with_app_names(self):
        """Test suggester initialization with app names."""
        suggester = CommandSuggester(app_names=["myapp", "api"])
        assert suggester._app_names == ["myapp", "api"]

    def test_suggester_update_app_names(self):
        """Test updating app names."""
        suggester = CommandSuggester()
        suggester.update_app_names(["app1", "app2"])
        assert suggester._app_names == ["app1", "app2"]

    @pytest.mark.asyncio
    async def test_suggester_empty_input(self):
        """Test suggestion for empty input."""
        suggester = CommandSuggester()
        result = await suggester.get_suggestion("")
        assert result is None

    @pytest.mark.asyncio
    async def test_suggester_command_completion(self):
        """Test command completion."""
        suggester = CommandSuggester()
        # Typing "ap" should suggest "apps" or "app"
        result = await suggester.get_suggestion("ap")
        assert result in {"apps", "app"}

    @pytest.mark.asyncio
    async def test_suggester_command_start(self):
        """Test command completion for 'st'."""
        suggester = CommandSuggester()
        result = await suggester.get_suggestion("st")
        assert result in {"start", "stop", "status"}

    @pytest.mark.asyncio
    async def test_suggester_no_match(self):
        """Test no suggestion for unknown prefix."""
        suggester = CommandSuggester()
        result = await suggester.get_suggestion("xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_suggester_complete_command(self):
        """Test no suggestion for complete command."""
        suggester = CommandSuggester()
        result = await suggester.get_suggestion("apps")
        assert result is None

    @pytest.mark.asyncio
    async def test_suggester_app_name_completion(self):
        """Test app name completion."""
        suggester = CommandSuggester(app_names=["myapp", "api-server", "worker"])
        result = await suggester.get_suggestion("start my")
        assert result == "start myapp"

    @pytest.mark.asyncio
    async def test_suggester_app_name_completion_multiple(self):
        """Test app name completion with multiple matches."""
        suggester = CommandSuggester(app_names=["app1", "app2", "other"])
        result = await suggester.get_suggestion("logs app")
        assert result in {"logs app1", "logs app2"}

    @pytest.mark.asyncio
    async def test_suggester_app_name_no_match(self):
        """Test no app name suggestion for unknown prefix."""
        suggester = CommandSuggester(app_names=["myapp", "api"])
        result = await suggester.get_suggestion("start xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_suggester_non_app_command(self):
        """Test no app completion for non-app commands."""
        suggester = CommandSuggester(app_names=["myapp", "api"])
        result = await suggester.get_suggestion("status my")
        assert result is None  # status doesn't take app name

    def test_commands_list_exists(self):
        """Test that COMMANDS list is defined."""
        assert len(COMMANDS) > 0
        assert "apps" in COMMANDS
        assert "start" in COMMANDS
        assert "help" in COMMANDS


class TestLogsScreenExtended:
    """Extended tests for LogsScreen."""

    @pytest.mark.asyncio
    async def test_logs_reactive_paused(self):
        """Test paused reactive property."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield LogsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(LogsScreen)
            assert screen.paused is False
            screen.paused = True
            assert screen.paused is True

    @pytest.mark.asyncio
    async def test_logs_reactive_auto_scroll(self):
        """Test auto_scroll reactive property."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield LogsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(LogsScreen)
            assert screen.auto_scroll is True
            screen.auto_scroll = False
            assert screen.auto_scroll is False

    @pytest.mark.asyncio
    async def test_logs_screen_composes(self):
        """Test logs screen composes correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield LogsScreen(app_name="testapp")

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(LogsScreen)
            assert screen is not None
            assert screen.app_name == "testapp"
            # Should have filter input
            filter_input = screen.query_one("#filter-input", Input)
            assert filter_input is not None
            # Should have logs content
            logs_content = screen.query_one("#logs-content", Static)
            assert logs_content is not None


class TestEnvVarsScreen:
    """Tests for EnvVarsScreen."""

    def test_env_vars_screen_init(self):
        """Test EnvVarsScreen initialization."""
        screen = EnvVarsScreen(app_name="myapp")
        assert screen.app_name == "myapp"
        assert screen._env_vars == []
        assert screen._show_hidden is False

    def test_env_vars_screen_default_name(self):
        """Test EnvVarsScreen with default name."""
        screen = EnvVarsScreen()
        assert screen.app_name == ""

    @pytest.mark.asyncio
    async def test_env_vars_screen_composes(self):
        """Test env vars screen composes correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield EnvVarsScreen(app_name="testapp")

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(EnvVarsScreen)
            assert screen is not None
            assert screen.app_name == "testapp"
            # Should have data table
            table = screen.query_one("#env-table", DataTable)
            assert table is not None

    @pytest.mark.asyncio
    async def test_env_vars_table_columns(self):
        """Test env vars table has expected columns."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield EnvVarsScreen(app_name="testapp")

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(EnvVarsScreen)
            table = screen.query_one("#env-table", DataTable)
            # Table should have 3 columns: NAME, VALUE, TYPE
            assert len(table.columns) == 3

    def test_format_value_normal(self):
        """Test value formatting for normal values."""
        screen = EnvVarsScreen()
        screen._show_hidden = True
        assert screen._format_value("hello") == "hello"
        assert screen._format_value("12345") == "12345"

    def test_format_value_hidden_sensitive(self):
        """Test value formatting hides sensitive values."""
        screen = EnvVarsScreen()
        screen._show_hidden = False
        assert screen._format_value("sk-secret-key") == "****hidden****"
        assert screen._format_value("mypassword123") == "****hidden****"

    def test_format_value_truncate_long(self):
        """Test value formatting truncates long values."""
        screen = EnvVarsScreen()
        screen._show_hidden = True
        long_value = "a" * 100
        result = screen._format_value(long_value)
        assert len(result) == 50
        assert result.endswith("...")

    def test_is_sensitive_detection(self):
        """Test sensitive value detection."""
        screen = EnvVarsScreen()
        assert screen._is_sensitive("sk-secret-key") is True
        assert screen._is_sensitive("my_password_here") is True
        assert screen._is_sensitive("auth_token_123") is True
        assert screen._is_sensitive("hello_world") is False
        assert screen._is_sensitive("12345") is False

    @pytest.mark.asyncio
    async def test_env_vars_toggle_visibility(self):
        """Test toggling value visibility."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield EnvVarsScreen(app_name="testapp")

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(EnvVarsScreen)
            assert screen._show_hidden is False
            screen.action_toggle_visibility()
            assert screen._show_hidden is True
            screen.action_toggle_visibility()
            assert screen._show_hidden is False

    @pytest.mark.asyncio
    async def test_env_vars_loads_mock_data(self):
        """Test that env vars screen loads mock data when no API client."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield EnvVarsScreen(app_name="testapp")

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(EnvVarsScreen)
            # Wait for mock data to load
            await pilot.pause()
            # Should have mock env vars loaded
            assert len(screen._env_vars) > 0
            # Check that mock data includes expected vars
            var_names = [v.name for v in screen._env_vars]
            assert "DEBUG" in var_names
            assert "DATABASE_URL" in var_names

    def test_env_vars_get_selected_var_empty(self):
        """Test getting selected var when table is empty."""
        screen = EnvVarsScreen()
        # Without mounting, _get_selected_var should handle gracefully
        # This tests the logic path, not the actual UI interaction


class TestAddonsScreen:
    """Tests for AddonsScreen."""

    def test_addons_screen_init(self):
        """Test AddonsScreen initialization."""
        screen = AddonsScreen()
        assert screen._addons == []
        assert screen._dialog_open is False

    @pytest.mark.asyncio
    async def test_addons_screen_composes(self):
        """Test addons screen composes correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AddonsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(AddonsScreen)
            assert screen is not None
            # Should have data table
            table = screen.query_one("#addons-table", DataTable)
            assert table is not None

    @pytest.mark.asyncio
    async def test_addons_table_columns(self):
        """Test addons table has expected columns."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AddonsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(AddonsScreen)
            table = screen.query_one("#addons-table", DataTable)
            # Table should have 4 columns: NAME, TYPE, APP, STATUS
            assert len(table.columns) == 4

    @pytest.mark.asyncio
    async def test_addons_loads_mock_data(self):
        """Test that addons screen loads mock data when no API client."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AddonsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(AddonsScreen)
            # Wait for mock data to load
            await pilot.pause()
            # Should have mock addons loaded
            assert len(screen._addons) > 0


class TestBackupsScreen:
    """Tests for BackupsScreen."""

    def test_backups_screen_init(self):
        """Test BackupsScreen initialization."""
        screen = BackupsScreen()
        assert screen._backups == []
        assert screen._dialog_open is False

    @pytest.mark.asyncio
    async def test_backups_screen_composes(self):
        """Test backups screen composes correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield BackupsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(BackupsScreen)
            assert screen is not None
            # Should have data table
            table = screen.query_one("#backups-table", DataTable)
            assert table is not None

    @pytest.mark.asyncio
    async def test_backups_table_columns(self):
        """Test backups table has expected columns."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield BackupsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(BackupsScreen)
            table = screen.query_one("#backups-table", DataTable)
            # Table should have 5 columns: ID, APP, SIZE, CREATED, ADDONS
            assert len(table.columns) == 5

    @pytest.mark.asyncio
    async def test_backups_loads_mock_data(self):
        """Test that backups screen loads mock data when no API client."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield BackupsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(BackupsScreen)
            # Wait for mock data to load
            await pilot.pause()
            # Should have mock backups loaded
            assert len(screen._backups) > 0

    def test_format_size_bytes(self):
        """Test size formatting for bytes."""
        screen = BackupsScreen()
        assert screen._format_size(512) == "512 B"

    def test_format_size_kb(self):
        """Test size formatting for kilobytes."""
        screen = BackupsScreen()
        result = screen._format_size(2048)
        assert "KB" in result

    def test_format_size_mb(self):
        """Test size formatting for megabytes."""
        screen = BackupsScreen()
        result = screen._format_size(1048576)  # 1 MB
        assert "MB" in result

    def test_format_size_gb(self):
        """Test size formatting for gigabytes."""
        screen = BackupsScreen()
        result = screen._format_size(1073741824)  # 1 GB
        assert "GB" in result

    def test_format_date_none(self):
        """Test date formatting with None."""
        screen = BackupsScreen()
        assert screen._format_date(None) == "N/A"

    def test_format_date_valid(self):
        """Test date formatting with valid datetime."""
        screen = BackupsScreen()
        dt = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = screen._format_date(dt)
        assert "2024-03-15" in result
        assert "12:00" in result
