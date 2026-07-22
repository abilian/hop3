# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[global-statement]
# `_service` is the singleton background worker. start/stop are called
# from Litestar lifespan hooks (see asgi.py), and the global is the
# handle they coordinate over. A Dishka provider would have to express
# both lifecycle and the start/stop API; the current shape is simpler.

"""Background service for synchronizing app states with reality.

This service periodically checks apps in transitional states (STARTING, STOPPING)
and updates them to their final states (RUNNING, STOPPED, FAILED) based on
actual process status.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from hop3.lib import log
from hop3.orm import App, AppRepository, AppStateEnum

if TYPE_CHECKING:
    from collections.abc import Callable

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
        # Re-attach native cgroup caps every ~60s, not every cycle: attaching is
        # an idempotent rootd round-trip per capped app, so doing it on the 3s
        # babysitter cadence would be wasteful. ponytail: a respawned vassal
        # master is uncapped for up to one window; tighten REATTACH_EVERY if that
        # window matters.
        self._cycle = 0
        self._reattach_every = max(1, round(60.0 / interval))

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
        self._cycle += 1
        with self.session_factory() as session:
            synced_count = self.sync_transitional_apps(session)
            if synced_count > 0:
                session.commit()
            if self._cycle % self._reattach_every == 0:
                self.reattach_native_limits(session)

    def reattach_native_limits(self, session: Session) -> None:
        """Re-assert cgroup caps on RUNNING native-capped apps (ADR 046 §3).

        Idempotent insurance against a whole-vassal respawn or a rootd restart
        leaving a running app outside its leaf. Best-effort and read-only on the
        DB — ``reattach_native_limits`` never raises, so a rootd hiccup can't
        break the babysitter loop. Public for direct testing without threading.
        """
        from hop3.deployers.native_limits import (  # ruff:ignore[import-outside-top-level]
            reattach_native_limits,
        )

        app_repo = AppRepository(session=session)
        for app in app_repo.list_by_run_states([AppStateEnum.RUNNING]):
            if app.limits_enforced == "native":
                reattach_native_limits(app.name)

    def sync_transitional_apps(self, session: Session) -> int:
        """Check all apps in transitional states and update them.

        This method is public to allow direct testing without threading.

        Args:
            session: Database session to use

        Returns:
            Number of apps whose state was updated
        """
        app_repo = AppRepository(session=session)
        apps = app_repo.list_transitional()

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
            app._transition_state(  # ruff:ignore[private-member-access]
                AppStateEnum.FAILED,
                f"Failed to start within {self.timeout:.0f}s",
            )
            log(
                f"App '{app.name}' start timed out after {self.timeout:.0f}s",
                level=1,
                fg="red",
            )
        elif app.run_state == AppStateEnum.STOPPING:
            # Stop has dragged on. Don't blindly report STOPPED — reap-and-verify
            # first, so a daemon that ignored the Emperor's SIGTERM (e.g. an
            # exec'd Nix binary holding a fixed port) can't be mislabelled STOPPED
            # while it still holds its port (the next deploy would then fail to
            # bind). Mirrors the reap-and-verify contract in App._stop_uwsgi.
            from hop3.run.reaper import (
                reap_app_processes,
            )

            survivors = reap_app_processes(app.name)
            if survivors:
                app._transition_state(  # ruff:ignore[private-member-access]
                    AppStateEnum.FAILED,
                    f"Stop timed out; {len(survivors)} process(es) still running",
                )
                log(
                    f"App '{app.name}' stop timed out and {len(survivors)} "
                    f"process(es) survived; marked FAILED (port still held)",
                    level=1,
                    fg="red",
                )
            else:
                app._transition_state(AppStateEnum.STOPPED)  # ruff:ignore[private-member-access]
                log(
                    f"App '{app.name}' stop timed out, reaped, forced to STOPPED",
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
