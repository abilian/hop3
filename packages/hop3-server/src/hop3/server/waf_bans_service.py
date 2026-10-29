# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[global-statement]
# `_service` is the singleton background worker; start/stop are called from
# Litestar lifespan hooks (see asgi.py), mirroring cert_renewal_service.py.

"""
Background service that reconciles Layer-7 WAF bans (ADR 050 §4).

This runs in the server process — the primary, in-process path for turning the
WAF audit stream into bans. (`hop3 waf reconcile-bans` is the on-demand
fallback.) Each cycle scores every WAF-enabled app's audit stream, bans repeat
offenders for the configured TTL, expires elapsed bans, and reloads a proxy only
when its denylist changed. Per-app failures are logged loudly and never abort
the cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from hop3.deployers.waf import reconcile_bans
from hop3.lib import log
from hop3.lib.logging import server_log
from hop3.orm import AppRepository

from .periodic_service import PeriodicService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

# Bans must bite quickly after a source crosses the violation threshold; the
# cycle is cheap (small audit reads) and reloads a proxy only on a real change.
RECONCILE_INTERVAL_SECONDS = 60.0
INITIAL_DELAY_SECONDS = 60.0


class WafBansService(PeriodicService):
    """
    Background service that reconciles WAF bans from the audit stream.

    Attributes:
        session_factory: Callable that returns a new database session.
        interval: Seconds between reconcile cycles.
        initial_delay: Seconds to wait before the first cycle (let the server settle).
    """

    name: ClassVar[str] = "waf-bans"

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        interval: float = RECONCILE_INTERVAL_SECONDS,
        initial_delay: float = INITIAL_DELAY_SECONDS,
    ) -> None:
        super().__init__(interval=interval, initial_delay=initial_delay)
        self.session_factory = session_factory

    def run_once(self) -> int:
        """
        Run one reconcile cycle across all apps; return the active-ban total.

        Public so it's testable without threading. Each app is committed
        independently so one broken app can't roll back or starve the others.
        """
        from hop3.project.config import (  # ruff:ignore[import-outside-top-level]
            AppConfig,
        )

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
