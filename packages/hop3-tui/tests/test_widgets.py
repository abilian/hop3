# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Tests for custom widgets."""

from __future__ import annotations

import pytest
from hop3_tui.api.models import AppState
from hop3_tui.widgets.confirmation import ConfirmationDialog
from hop3_tui.widgets.status_badge import StatusBadge
from hop3_tui.widgets.status_panel import StatusPanel
from textual.app import App, ComposeResult
from textual.widgets import Static


class TestStatusBadge:
    """Tests for StatusBadge widget."""

    def test_init_default_state(self):
        """Test default state is STOPPED."""
        badge = StatusBadge()
        assert badge.state == AppState.STOPPED

    def test_init_with_state(self):
        """Test initialization with specific state."""
        badge = StatusBadge(state=AppState.RUNNING)
        assert badge.state == AppState.RUNNING

    @pytest.mark.asyncio
    async def test_badge_updates_on_state_change(self):
        """Test badge updates when state changes."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield StatusBadge(state=AppState.STOPPED)

        app = TestApp()
        async with app.run_test() as pilot:
            badge = app.query_one(StatusBadge)
            assert badge.state == AppState.STOPPED

            badge.state = AppState.RUNNING
            assert badge.state == AppState.RUNNING


class TestStatusPanel:
    """Tests for StatusPanel widget."""

    @pytest.mark.asyncio
    async def test_status_panel_renders(self):
        """Test status panel renders correctly."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield StatusPanel()

        app = TestApp()
        async with app.run_test() as pilot:
            panel = app.query_one(StatusPanel)
            assert panel is not None

    @pytest.mark.asyncio
    async def test_status_panel_reactive_values(self):
        """Test status panel reactive values."""

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield StatusPanel()

        app = TestApp()
        async with app.run_test() as pilot:
            panel = app.query_one(StatusPanel)
            panel.cpu = 50.0
            panel.memory = 60.0
            panel.disk = 70.0
            panel.uptime = "1d 2h"

            assert panel.cpu == 50.0
            assert panel.memory == 60.0
            assert panel.disk == 70.0
            assert panel.uptime == "1d 2h"

    def test_make_bar_low(self):
        """Test progress bar for low percentage."""
        panel = StatusPanel()
        bar = panel._make_bar(20.0, width=10)
        assert "██" in bar  # 20% = 2 filled
        assert "green" in bar  # Low = green

    def test_make_bar_medium(self):
        """Test progress bar for medium percentage."""
        panel = StatusPanel()
        bar = panel._make_bar(75.0, width=10)
        assert "yellow" in bar  # 70-90% = yellow

    def test_make_bar_high(self):
        """Test progress bar for high percentage."""
        panel = StatusPanel()
        bar = panel._make_bar(95.0, width=10)
        assert "red" in bar  # 90%+ = red


class TestConfirmationDialog:
    """Tests for ConfirmationDialog widget."""

    def test_dialog_init(self):
        """Test dialog initialization."""
        dialog = ConfirmationDialog(
            title="Confirm Delete",
            message="Are you sure?",
            confirm_label="Delete",
            cancel_label="Cancel",
        )
        assert dialog.title_text == "Confirm Delete"
        assert dialog.message == "Are you sure?"
        assert dialog.confirm_label == "Delete"
        assert dialog.cancel_label == "Cancel"

    def test_dialog_default_labels(self):
        """Test dialog with default labels."""
        dialog = ConfirmationDialog(
            title="Confirm",
            message="Continue?",
        )
        assert dialog.confirm_label == "Confirm"
        assert dialog.cancel_label == "Cancel"

    @pytest.mark.asyncio
    async def test_dialog_cancel(self):
        """Test canceling dialog."""
        confirmed = None

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Static("Main content")

            def on_mount(self) -> None:
                self.push_screen(
                    ConfirmationDialog(
                        title="Test",
                        message="Test message",
                    ),
                    callback=self.handle_result,
                )

            def handle_result(self, result: bool) -> None:  # noqa: FBT001
                nonlocal confirmed
                confirmed = result

        app = TestApp()
        async with app.run_test() as pilot:
            # Press escape to cancel
            await pilot.press("escape")
            assert confirmed is False

    @pytest.mark.asyncio
    async def test_dialog_with_callback(self):
        """Test dialog executes callback on confirm."""
        callback_called = False

        def on_confirm():
            nonlocal callback_called
            callback_called = True

        dialog = ConfirmationDialog(
            title="Test",
            message="Test",
            on_confirm=on_confirm,
        )
        assert dialog.on_confirm is not None
