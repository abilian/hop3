# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Domain registration (WHOIS) + DNS health for app domains.

Read-only and best-effort: every probe degrades to "unknown" on error (WHOIS
rate limits, network failures, DNS issues) and never raises, so a slow or
blocked lookup can't break the dashboard or the background collector.

Results live in a small in-memory snapshot populated by the background collector
(server/domain_health_service.py) and read by the dashboard — WHOIS is too slow
and rate-limited to query on a page load.
"""

from __future__ import annotations

import datetime
import socket
from contextlib import suppress
from dataclasses import dataclass, field

import whois

# Flag a domain registration expiring within this many days.
REGISTRATION_WARNING_DAYS = 30

# RFC1918 / loopback prefixes: a server IP in these ranges is almost certainly a
# private/NAT address, so a DNS-points-here comparison against it is unreliable.
_PRIVATE_PREFIXES = (
    "10.",
    "127.",
    "192.168.",
    "169.254.",
    *(f"172.{n}." for n in range(16, 32)),
)


@dataclass(frozen=True)
class DomainHealth:
    domain: str
    registration_expiry: datetime.date | None = None
    registration_days_left: int | None = None
    resolves: bool | None = None  # does it resolve to any address?
    points_here: bool | None = (
        None  # resolves to one of this server's IPs? (None=unknown)
    )
    resolved_ips: tuple[str, ...] = ()
    checked_at: datetime.datetime | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


def check_domain(
    domain: str,
    *,
    server_ips: frozenset[str] = frozenset(),
    now: datetime.datetime | None = None,
) -> DomainHealth:
    """Probe one domain's registration expiry (WHOIS) and DNS — never raises."""
    now = now or datetime.datetime.now(datetime.UTC)
    notes: list[str] = []

    expiry = _whois_expiry(domain)
    days_left: int | None = None
    if expiry is None:
        notes.append("registration expiry unknown (WHOIS lookup failed)")
    else:
        days_left = (expiry - now.date()).days
        if days_left < 0:
            notes.append(f"registration expired {-days_left}d ago")
        elif days_left < REGISTRATION_WARNING_DAYS:
            notes.append(f"registration expires in {days_left}d")

    ips = _resolve(domain)
    resolves = bool(ips)
    points_here: bool | None = None
    if not resolves:
        notes.append("does not resolve (DNS lookup failed)")
    else:
        usable = {ip for ip in server_ips if not ip.startswith(_PRIVATE_PREFIXES)}
        if usable:
            points_here = any(ip in usable for ip in ips)
            if not points_here:
                notes.append(f"DNS points to {', '.join(sorted(ips))}, not this server")

    return DomainHealth(
        domain=domain,
        registration_expiry=expiry,
        registration_days_left=days_left,
        resolves=resolves,
        points_here=points_here,
        resolved_ips=ips,
        checked_at=now,
        notes=tuple(notes),
    )


def server_ips() -> frozenset[str]:
    """Best-effort set of this host's own IPs (to detect mis-pointed DNS).

    Combines the primary outbound-route IP and the resolved hostname. Under NAT
    these may be private addresses; check_domain ignores private IPs for the
    points-here comparison rather than raising a false alarm.
    """
    ips: set[str] = set()
    with suppress(OSError):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))  # sets the route; sends nothing
            ips.add(sock.getsockname()[0])
        finally:
            sock.close()
    with suppress(OSError):
        ips.update(
            str(info[4][0]) for info in socket.getaddrinfo(socket.gethostname(), None)
        )
    return frozenset(ips)


def _whois_expiry(domain: str) -> datetime.date | None:
    try:
        data = whois.whois(domain)
    except Exception:
        return None
    expiry = getattr(data, "expiration_date", None) if data else None
    if isinstance(expiry, list):
        expiry = next((e for e in expiry if e), None)
    if isinstance(expiry, datetime.datetime):
        return expiry.date()
    if isinstance(expiry, datetime.date):
        return expiry
    return None


def _resolve(domain: str) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(domain, None)
    except OSError:
        return ()
    return tuple(sorted({str(info[4][0]) for info in infos}))


# In-memory snapshot, populated by the background collector and read by the
# dashboard (the data is ephemeral; recomputed after a restart).
_snapshot: dict[str, DomainHealth] = {}


def set_domain_health(results: dict[str, DomainHealth]) -> None:
    global _snapshot  # noqa: PLW0603
    _snapshot = dict(results)


def get_domain_health(domain: str) -> DomainHealth | None:
    return _snapshot.get(domain)


def all_domain_health() -> dict[str, DomainHealth]:
    return dict(_snapshot)
