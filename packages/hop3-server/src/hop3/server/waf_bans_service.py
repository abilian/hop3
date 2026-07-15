# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: PLW0603
# `_service` is the singleton background worker; start/stop are called from
# Litestar lifespan hooks (see asgi.py), mirroring cert_renewal_service.py.

"""Background service that reconciles Layer-7 WAF bans (ADR 050 §4).

This runs in the server process — the primary, in-process path for turning the
WAF audit stream into bans. (`hop3 waf reconcile-bans` is the on-demand
fallback.) Each cycle scores every WAF-enabled app's audit stream, bans repeat
offenders for the configured TTL, expires elapsed bans, and reloads a proxy only
when its denylist changed. Per-app failures are logged loudly and never abort
the cycle.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from hop3.deployers.waf import reconcile_bans
from hop3.lib import log
from hop3.lib.logging import server_log
from hop3.orm import AppRepository

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

# Bans must bite quickly after a source crosses the violation threshold; the
# cycle is cheap (small audit reads) and reloads a proxy only on a real change.
RECONCILE_INTERVAL_SECONDS = 60.0
INITIAL_DELAY_SECONDS = 60.0


class WafBansService:
    """Background service that reconciles WAF bans from the audit stream.

    Attributes:
        session_factory: Callable that returns a new database session.
        interval: Seconds between reconcile cycles.
        initial_delay: Seconds to wait before the first cycle (let the server settle).
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        interval: float = RECONCILE_INTERVAL_SECONDS,
        initial_delay: float = INITIAL_DELAY_SECONDS,
    ):
        self.session_factory = session_factory
        self.interval = interval
        self.initial_delay = initial_delay
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background reconcile thread."""
        if self._thread is not None and self._thread.is_alive():
            log("WAF ban service already running", level=2, fg="yellow")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="waf-bans", daemon=True)
        self._thread.start()
        log("WAF ban service started", level=1, fg="green")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background reconcile thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        log("WAF ban service stopped", level=1, fg="yellow")

    def is_running(self) -> bool:
        """Check if the service is currently running."""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        """Main loop: a short settle delay, then a cycle every interval."""
        delay = self.initial_delay
        while not self._stop_event.wait(delay):
            delay = self.interval
            try:
                self.run_once()
            except Exception as e:
                log(f"WAF ban reconcile error: {e}", level=1, fg="red")
                server_log.exception("WAF ban reconcile cycle failed", error=str(e))

    def run_once(self) -> int:
        """Run one reconcile cycle across all apps; return the active-ban total.

        Public so it's testable without threading. Each app is committed
        independently so one broken app can't roll back or starve the others.
        """
        from hop3.project.config import AppConfig  # noqa: PLC0415 - avoid import cycle

        active_total = 0
        with self.session_factory() as session:
            apps = AppRepository(session=session).list_all_ordered()
            for app in apps:
                try:
                    app_config = AppConfig.from_dir(app.app_path)
                    active_total += reconcile_bans(app, app_config, session)
                    session.commit()
                except Exception as e:
                    session.rollback()
                    log(
                        f"✗ WAF ban reconcile failed for {app.name}: {e}",
                        level=1,
                        fg="red",
                    )
                    server_log.exception(
                        "WAF ban reconcile failed", app=app.name, error=str(e)
                    )
        return active_total


# Global instance for server integration (mirrors cert_renewal_service.py).
_service: WafBansService | None = None


def get_waf_bans_service() -> WafBansService | None:
    """Get the global WAF ban service instance."""
    return _service


def start_waf_bans_service(
    session_factory: Callable[[], Session],
) -> WafBansService:
    """Start the global WAF ban service."""
    global _service
    if _service is not None and _service.is_running():
        return _service
    _service = WafBansService(session_factory)
    _service.start()
    return _service


def stop_waf_bans_service() -> None:
    """Stop the global WAF ban service."""
    global _service
    if _service is not None:
        _service.stop()
        _service = None
