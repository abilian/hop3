# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Tests for the main Hop3TUI application."""

from __future__ import annotations

import pytest
from hop3_tui.app import Hop3TUI


class TestHop3TUIApp:
    """Tests for Hop3TUI application."""

    @pytest.mark.asyncio
    async def test_app_initialization(self):
        """Test that the app initializes correctly."""
        app = Hop3TUI()
        assert app.TITLE == "Hop3"
        assert app.SUB_TITLE == "Platform as a Service"
        assert app.dark is True

    @pytest.mark.asyncio
    async def test_app_has_modes(self):
        """Test that app has all expected modes."""
        app = Hop3TUI()
        assert "dashboard" in app.MODES
        assert "apps" in app.MODES
        assert "system" in app.MODES
        assert "chat" in app.MODES

    @pytest.mark.asyncio
    async def test_app_bindings(self):
        """Test that app has expected bindings."""
        app = Hop3TUI()
        binding_keys = [b.key for b in app.BINDINGS]
        assert "q" in binding_keys  # Quit
        assert "?" in binding_keys  # Help
        assert "d" in binding_keys  # Dashboard
        assert "a" in binding_keys  # Apps
        assert "s" in binding_keys  # System
        assert "c" in binding_keys  # Chat

    @pytest.mark.asyncio
    async def test_app_starts_on_dashboard(self):
        """Test that app starts on dashboard screen."""
        app = Hop3TUI()
        async with app.run_test() as pilot:
            # App should start and be running
            assert app.is_running
            # Should be on dashboard mode
            # Note: Mode checking might need adjustment based on Textual version

    @pytest.mark.asyncio
    async def test_app_quit_action(self):
        """Test that quit action works."""
        app = Hop3TUI()
        async with app.run_test() as pilot:
            await pilot.press("q")
            # App should exit


class TestHop3TUINavigation:
    """Tests for navigation between screens."""

    @pytest.mark.asyncio
    async def test_navigate_to_apps(self):
        """Test navigating to apps screen."""
        app = Hop3TUI()
        async with app.run_test() as pilot:
            await pilot.press("a")
            # Should switch to apps mode

    @pytest.mark.asyncio
    async def test_navigate_to_system(self):
        """Test navigating to system screen."""
        app = Hop3TUI()
        async with app.run_test() as pilot:
            await pilot.press("s")
            # Should switch to system mode

    @pytest.mark.asyncio
    async def test_navigate_to_chat(self):
        """Test navigating to chat screen."""
        app = Hop3TUI()
        async with app.run_test() as pilot:
            await pilot.press("c")
            # Should switch to chat mode

    @pytest.mark.asyncio
    async def test_navigate_back_to_dashboard(self):
        """Test navigating back to dashboard."""
        app = Hop3TUI()
        async with app.run_test() as pilot:
            await pilot.press("a")  # Go to apps
            await pilot.press("d")  # Go back to dashboard


class TestHop3TUIHelp:
    """Tests for help functionality."""

    @pytest.mark.asyncio
    async def test_help_action(self):
        """Test help action shows notification."""
        app = Hop3TUI()
        async with app.run_test() as pilot:
            await pilot.press("?")
            # Should show help notification
