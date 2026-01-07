# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Background service for synchronizing app states with reality.

This service periodically checks apps in transitional states (STARTING, STOPPING)
and updates them to their final states (RUNNING, STOPPED, FAILED) based on
actual process status.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from hop3.lib import log
from hop3.orm import App, AppStateEnum

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class StateSyncService:
    """Background service that syncs transitional app states with reality.

    This service runs in a background thread and periodically:
    1. Finds all apps in STARTING or STOPPING state
    2. Checks their actual status (port listening, process running)
    3. Updates the database to reflect reality
    4. Handles timeouts (apps stuck in transitional states)

    Attributes:
        session_factory: Callable that returns a new database session
        interval: Seconds between sync cycles (default: 3.0)
        timeout: Max seconds an app can stay in transitional state (default: 60.0)
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        interval: float = 3.0,
        timeout: float = 60.0,
    ):
        """Initialize the state sync service.

        Args:
            session_factory: Factory function that creates database sessions
            interval: How often to check transitional states (seconds)
            timeout: How long before a transitional state is considered timed out
        """
        self.session_factory = session_factory
        self.interval = interval
        self.timeout = timeout
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background sync thread."""
        if self._thread is not None and self._thread.is_alive():
            log("State sync service already running", level=2, fg="yellow")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="state-sync",
            daemon=True,
        )
        self._thread.start()
        log("State sync service started", level=1, fg="green")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background sync thread.

        Args:
            timeout: Max seconds to wait for thread to stop
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        log("State sync service stopped", level=1, fg="yellow")

    def is_running(self) -> bool:
        """Check if the service is currently running."""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        """Main loop - runs until stopped."""
        while not self._stop_event.wait(self.interval):
            try:
                self._sync_cycle()
            except Exception as e:
                log(f"State sync error: {e}", level=1, fg="red")

    def _sync_cycle(self) -> None:
        """Run one sync cycle - check all transitional apps."""
        with self.session_factory() as session:
            synced_count = self.sync_transitional_apps(session)
            if synced_count > 0:
                session.commit()

    def sync_transitional_apps(self, session: Session) -> int:
        """Check all apps in transitional states and update them.

        This method is public to allow direct testing without threading.

        Args:
            session: Database session to use

        Returns:
            Number of apps whose state was updated
        """
        apps = (
            session
            .query(App)
            .filter(App.run_state.in_([AppStateEnum.STARTING, AppStateEnum.STOPPING]))
            .all()
        )

        synced_count = 0
        for app in apps:
            if self._sync_app(app):
                synced_count += 1

        return synced_count

    def _sync_app(self, app: App) -> bool:
        """Sync a single app's state with reality.

        Args:
            app: The app to sync

        Returns:
            True if app state was changed, False otherwise
        """
        # Check for timeout first
        if self._is_timed_out(app):
            self._handle_timeout(app)
            return True

        # Normal sync - check actual status and update if needed
        return app.sync_state()

    def _is_timed_out(self, app: App) -> bool:
        """Check if app has been in transitional state too long.

        Args:
            app: The app to check

        Returns:
            True if app has exceeded the timeout, False otherwise
        """
        state_changed_at = getattr(app, "state_changed_at", None)
        if state_changed_at is None:
            return False

        elapsed = datetime.now(UTC) - state_changed_at.replace(tzinfo=UTC)
        return elapsed > timedelta(seconds=self.timeout)

    def _handle_timeout(self, app: App) -> None:
        """Handle an app that's been in transitional state too long.

        Args:
            app: The timed-out app
        """
        if app.run_state == AppStateEnum.STARTING:
            # Failed to start in time
            app._transition_state(  # noqa: SLF001
                AppStateEnum.FAILED,
                f"Failed to start within {self.timeout:.0f}s",
            )
            log(
                f"App '{app.name}' start timed out after {self.timeout:.0f}s",
                level=1,
                fg="red",
            )
        elif app.run_state == AppStateEnum.STOPPING:
            # Force to stopped - we already removed config files
            app._transition_state(AppStateEnum.STOPPED)  # noqa: SLF001
            log(
                f"App '{app.name}' stop timed out, forced to STOPPED",
                level=1,
                fg="yellow",
            )


# Global instance for server integration
_service: StateSyncService | None = None


def get_state_sync_service() -> StateSyncService | None:
    """Get the global state sync service instance."""
    return _service


def start_state_sync_service(
    session_factory: Callable[[], Session],
) -> StateSyncService:
    """Start the global state sync service.

    Args:
        session_factory: Factory function that creates database sessions

    Returns:
        The started service instance
    """
    global _service
    if _service is not None and _service.is_running():
        return _service

    _service = StateSyncService(session_factory)
    _service.start()
    return _service


def stop_state_sync_service() -> None:
    """Stop the global state sync service."""
    global _service
    if _service is not None:
        _service.stop()
        _service = None
