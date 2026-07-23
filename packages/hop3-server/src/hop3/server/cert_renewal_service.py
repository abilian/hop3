# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[global-statement]
# `_service` is the singleton background worker; start/stop are called from
# Litestar lifespan hooks (see asgi.py), mirroring state_sync.py.

"""
Background service that renews TLS certificates before they expire.

This runs in the server process — the primary, in-process maintenance path.
(`hop3 cert renew` is a debug-only fallback.) Each cycle renews every app's cert
that is within the threshold of expiry, reinstalls renewed certs into the proxy,
and reloads it. Per-app failures are logged loudly and never abort the cycle.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from hop3.lib import log
from hop3.lib.logging import server_log
from hop3.orm import AppRepository
from hop3.platform.cert_renewal import renew_due_certs
from hop3.platform.certificates import reload_nginx

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from hop3.platform.cert_renewal import RenewOutcome

# Twice-daily, matching certbot's convention. Renewal only acts inside the
# threshold window, so the exact cadence doesn't matter much.
RENEWAL_INTERVAL_SECONDS = 12 * 60 * 60
INITIAL_DELAY_SECONDS = 60.0
RENEWAL_THRESHOLD_DAYS = 30


class CertRenewalService:
    """
    Background service that renews app TLS certificates before expiry.

    Attributes:
        session_factory: Callable that returns a new database session.
        interval: Seconds between renewal cycles.
        initial_delay: Seconds to wait before the first cycle (let the server settle).
        threshold_days: Renew certs expiring within this many days.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        interval: float = RENEWAL_INTERVAL_SECONDS,
        initial_delay: float = INITIAL_DELAY_SECONDS,
        threshold_days: int = RENEWAL_THRESHOLD_DAYS,
    ):
        self.session_factory = session_factory
        self.interval = interval
        self.initial_delay = initial_delay
        self.threshold_days = threshold_days
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background renewal thread."""
        if self._thread is not None and self._thread.is_alive():
            log("Cert renewal service already running", level=2, fg="yellow")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="cert-renewal", daemon=True
        )
        self._thread.start()
        log("Cert renewal service started", level=1, fg="green")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background renewal thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        log("Cert renewal service stopped", level=1, fg="yellow")

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
                log(f"Cert renewal error: {e}", level=1, fg="red")
                server_log.exception("Cert renewal cycle failed", error=str(e))

    def run_once(self) -> RenewOutcome:
        """Run one renewal cycle. Public so it can be tested without threading."""
        with self.session_factory() as session:
            apps = AppRepository(session=session).list_all_ordered()
            outcome = renew_due_certs(apps, threshold_days=self.threshold_days)

        if outcome.renewed:
            reload_nginx()
            log(
                f"Renewed {len(outcome.renewed)} certificate(s): "
                + ", ".join(outcome.renewed),
                level=1,
                fg="green",
            )
        for label, err in outcome.failed:
            log(f"✗ Cert renewal failed for {label}: {err}", level=1, fg="red")
            server_log.error("Cert renewal failed", target=label, error=err)
        if outcome.failed:
            _notify_renewal_failures(outcome.failed)
        return outcome


def _notify_renewal_failures(failed: list[tuple[str, str]]) -> None:
    """
    Best-effort operator alert for cert-renewal failures.

    A no-op unless the operator enabled notifications (`server email
    notifications on`); never raises, so it can't disrupt the renewal cycle.
    Imported lazily to keep the email plugin off the service's import path.
    """
    from hop3.plugins.email.notifications import (  # ruff:ignore[import-outside-top-level]
        notify,
    )

    body = "\n".join(f"- {label}: {err}" for label, err in failed)
    notify(
        "cert-renewal-failure",
        f"[Hop3] {len(failed)} certificate renewal(s) failed",
        "Certificate renewal failed for:\n\n"
        + body
        + "\n\nThese certificates will expire if not renewed. Check the server "
        "logs and `hop3 cert renew`.",
    )


# Global instance for server integration (mirrors state_sync.py).
_service: CertRenewalService | None = None


def get_cert_renewal_service() -> CertRenewalService | None:
    """Get the global cert renewal service instance."""
    return _service


def start_cert_renewal_service(
    session_factory: Callable[[], Session],
) -> CertRenewalService:
    """Start the global cert renewal service."""
    global _service
    if _service is not None and _service.is_running():
        return _service
    _service = CertRenewalService(session_factory)
    _service.start()
    return _service


def stop_cert_renewal_service() -> None:
    """Stop the global cert renewal service."""
    global _service
    if _service is not None:
        _service.stop()
        _service = None
