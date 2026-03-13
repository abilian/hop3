# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the StateSyncService background service."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from hop3.orm import AppStateEnum
from hop3.server.state_sync import StateSyncService


class MockApp:
    """Mock App for testing without database."""

    def __init__(
        self,
        name: str,
        run_state: AppStateEnum,
        state_changed_at: datetime | None = None,
    ):
        self.name = name
        self.run_state = run_state
        self.state_changed_at = state_changed_at
        self.error_message = ""
        self._sync_state_called = False
        self._sync_state_returns = False

    def sync_state(self) -> bool:
        """Mock sync_state that can be configured to return True/False."""
        self._sync_state_called = True
        return self._sync_state_returns

    def _transition_state(self, new_state: AppStateEnum, error_msg: str = "") -> None:
        """Mock _transition_state that just updates the state."""
        self.run_state = new_state
        self.state_changed_at = datetime.now(UTC)
        if error_msg:
            self.error_message = error_msg


class MockSession:
    """Mock SQLAlchemy session for testing."""

    def __init__(self, apps: list[MockApp] | None = None):
        self.apps = apps or []
        self._committed = False

    def scalars(self, statement):
        """Mock scalars method for SQLAlchemy 2.0 select() API."""
        return self

    def all(self):
        return self.apps

    def commit(self):
        self._committed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestStateSyncService:
    """Tests for StateSyncService."""

    def test_init(self):
        """Test service initialization with default values."""
        service = StateSyncService(MockSession)
        assert service.interval == 3.0
        assert service.timeout == 60.0
        assert not service.is_running()

    def test_init_custom_values(self):
        """Test service initialization with custom values."""
        service = StateSyncService(
            MockSession,
            interval=5.0,
            timeout=30.0,
        )
        assert service.interval == 5.0
        assert service.timeout == 30.0

    def test_start_stop(self):
        """Test starting and stopping the service."""
        service = StateSyncService(MockSession, interval=0.1)

        service.start()
        assert service.is_running()

        service.stop()
        assert not service.is_running()

    def test_start_twice_is_safe(self):
        """Test that starting twice doesn't create multiple threads."""
        service = StateSyncService(MockSession, interval=0.1)

        service.start()
        service.start()  # Should not raise or create duplicate threads
        assert service.is_running()

        service.stop()

    @patch("hop3.server.state_sync.AppRepository")
    def test_sync_transitional_apps_starting(self, mock_repo_class):
        """Test syncing an app in STARTING state."""
        app = MockApp("test-app", AppStateEnum.STARTING)
        app._sync_state_returns = True  # Simulate sync updating state

        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.list_transitional.return_value = [app]
        mock_repo_class.return_value = mock_repo

        session = MockSession([app])
        service = StateSyncService(lambda: session)

        count = service.sync_transitional_apps(session)

        assert count == 1
        assert app._sync_state_called

    @patch("hop3.server.state_sync.AppRepository")
    def test_sync_transitional_apps_stopping(self, mock_repo_class):
        """Test syncing an app in STOPPING state."""
        app = MockApp("test-app", AppStateEnum.STOPPING)
        app._sync_state_returns = True

        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.list_transitional.return_value = [app]
        mock_repo_class.return_value = mock_repo

        session = MockSession([app])
        service = StateSyncService(lambda: session)

        count = service.sync_transitional_apps(session)

        assert count == 1
        assert app._sync_state_called

    @patch("hop3.server.state_sync.AppRepository")
    def test_sync_no_transitional_apps(self, mock_repo_class):
        """Test syncing when no apps are in transitional states."""
        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.list_transitional.return_value = []
        mock_repo_class.return_value = mock_repo

        session = MockSession([])
        service = StateSyncService(lambda: session)

        count = service.sync_transitional_apps(session)

        assert count == 0

    @patch("hop3.server.state_sync.AppRepository")
    def test_sync_app_not_changed(self, mock_repo_class):
        """Test syncing an app where state doesn't change."""
        app = MockApp("test-app", AppStateEnum.STARTING)
        app._sync_state_returns = False  # Sync doesn't change state

        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.list_transitional.return_value = [app]
        mock_repo_class.return_value = mock_repo

        session = MockSession([app])
        service = StateSyncService(lambda: session)

        count = service.sync_transitional_apps(session)

        assert count == 0
        assert app._sync_state_called

    @patch("hop3.server.state_sync.AppRepository")
    def test_timeout_starting_to_failed(self, mock_repo_class):
        """Test that STARTING apps time out to FAILED state."""
        # App has been in STARTING for 2 minutes
        old_time = datetime.now(UTC) - timedelta(minutes=2)
        app = MockApp("test-app", AppStateEnum.STARTING, state_changed_at=old_time)

        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.list_transitional.return_value = [app]
        mock_repo_class.return_value = mock_repo

        session = MockSession([app])
        service = StateSyncService(lambda: session, timeout=60.0)

        service.sync_transitional_apps(session)

        assert app.run_state == AppStateEnum.FAILED
        assert "Failed to start" in app.error_message

    @patch("hop3.server.state_sync.AppRepository")
    def test_timeout_stopping_to_stopped(self, mock_repo_class):
        """Test that STOPPING apps time out to STOPPED state."""
        # App has been in STOPPING for 2 minutes
        old_time = datetime.now(UTC) - timedelta(minutes=2)
        app = MockApp("test-app", AppStateEnum.STOPPING, state_changed_at=old_time)

        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.list_transitional.return_value = [app]
        mock_repo_class.return_value = mock_repo

        session = MockSession([app])
        service = StateSyncService(lambda: session, timeout=60.0)

        service.sync_transitional_apps(session)

        assert app.run_state == AppStateEnum.STOPPED

    @patch("hop3.server.state_sync.AppRepository")
    def test_no_timeout_within_limit(self, mock_repo_class):
        """Test that apps within timeout limit are not timed out."""
        # App has been in STARTING for 30 seconds (under 60s timeout)
        recent_time = datetime.now(UTC) - timedelta(seconds=30)
        app = MockApp("test-app", AppStateEnum.STARTING, state_changed_at=recent_time)
        app._sync_state_returns = False

        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.list_transitional.return_value = [app]
        mock_repo_class.return_value = mock_repo

        session = MockSession([app])
        service = StateSyncService(lambda: session, timeout=60.0)

        service.sync_transitional_apps(session)

        # Should still be STARTING (sync was called but returned False)
        assert app.run_state == AppStateEnum.STARTING
        assert app._sync_state_called

    @patch("hop3.server.state_sync.AppRepository")
    def test_no_timeout_without_timestamp(self, mock_repo_class):
        """Test that apps without state_changed_at are not timed out."""
        app = MockApp("test-app", AppStateEnum.STARTING, state_changed_at=None)
        app._sync_state_returns = False

        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.list_transitional.return_value = [app]
        mock_repo_class.return_value = mock_repo

        session = MockSession([app])
        service = StateSyncService(lambda: session, timeout=60.0)

        service.sync_transitional_apps(session)

        # Should still be STARTING (no timeout applied)
        assert app.run_state == AppStateEnum.STARTING
        assert app._sync_state_called


class TestStateSyncServiceIntegration:
    """Integration-style tests for the background loop."""

    @patch("hop3.server.state_sync.AppRepository")
    def test_sync_cycle_commits_on_change(self, mock_repo_class):
        """Test that sync cycle commits when state changes."""
        app = MockApp("test-app", AppStateEnum.STARTING)
        app._sync_state_returns = True

        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.list_transitional.return_value = [app]
        mock_repo_class.return_value = mock_repo

        session = MockSession([app])
        service = StateSyncService(lambda: session)

        service._sync_cycle()

        assert session._committed

    @patch("hop3.server.state_sync.AppRepository")
    def test_sync_cycle_no_commit_on_no_change(self, mock_repo_class):
        """Test that sync cycle doesn't commit when no state changes."""
        # Mock the repository
        mock_repo = MagicMock()
        mock_repo.list_transitional.return_value = []
        mock_repo_class.return_value = mock_repo

        session = MockSession([])  # No apps
        service = StateSyncService(lambda: session)

        service._sync_cycle()

        assert not session._committed

    def test_background_thread_runs(self):
        """Test that background thread actually runs sync cycles."""
        sync_count = {"value": 0}

        def mock_sync_cycle():
            sync_count["value"] += 1

        service = StateSyncService(MockSession, interval=0.05)
        service._sync_cycle = mock_sync_cycle

        service.start()
        time.sleep(0.2)  # Allow a few cycles
        service.stop()

        assert sync_count["value"] >= 2  # At least 2 cycles should have run
