# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[global-statement]
# `_service` is the singleton background worker; start/stop are called from
# Litestar lifespan hooks (see asgi.py), mirroring state_sync.py / cert_renewal.

"""
Background service that probes app domains' registration + DNS health.

An in-process maintenance task (like CertRenewalService / StateSyncService).
Each cycle checks every app domain's WHOIS registration expiry and DNS, and
stores the result for the dashboard. WHOIS is rate-limited, so it runs daily.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from hop3.lib import log
from hop3.orm import AppRepository
from hop3.platform.cert_renewal import app_cert_domain
from hop3.platform.domain_health import check_domain, server_ips, set_domain_health

from .periodic_service import PeriodicService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from hop3.platform.domain_health import DomainHealth

# WHOIS is rate-limited; once a day is ample for registration expiry.
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
INITIAL_DELAY_SECONDS = 120.0


class DomainHealthService(PeriodicService):
    """Background service probing app domains' WHOIS + DNS health."""

    name: ClassVar[str] = "domain-health"

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        interval: float = CHECK_INTERVAL_SECONDS,
        initial_delay: float = INITIAL_DELAY_SECONDS,
    ) -> None:
        super().__init__(interval=interval, initial_delay=initial_delay)
        self.session_factory = session_factory

    def run_once(self) -> dict[str, DomainHealth]:
        """Probe every app domain and refresh the snapshot. Public for testing."""
        with self.session_factory() as session:
            apps = AppRepository(session=session).list_all_ordered()
            domains = sorted({d for app in apps if (d := app_cert_domain(app))})

        ips = server_ips()
        results = {d: check_domain(d, server_ips=ips) for d in domains}
        set_domain_health(results)

        for health in results.values():
            if health.notes:
                log(
                    f"Domain health: {health.domain}: {'; '.join(health.notes)}",
                    level=2,
                    fg="yellow",
                )
        return results


# Global instance for server integration (mirrors state_sync.py).
_service: DomainHealthService | None = None


def get_domain_health_service() -> DomainHealthService | None:
    return _service


def start_domain_health_service(
    session_factory: Callable[[], Session],
) -> DomainHealthService:
    global _service
    if _service is not None and _service.is_running():
        return _service
    _service = DomainHealthService(session_factory)
    _service.start()
    return _service


def stop_domain_health_service() -> None:
    global _service
    if _service is not None:
        _service.stop()
        _service = None
