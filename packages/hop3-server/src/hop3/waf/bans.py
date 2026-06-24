# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""L7 ban scoring (ADR 050 §4) — pure logic over the WAF audit stream.

Given the structured ``blocked`` events the proxy emits, decide which sources
have crossed the threshold within the scoring window. Kept side-effect-free (no
DB, no files, no clock) so it's exhaustively testable; the orchestration that
reads the audit log, writes the ban DB, regenerates the denylist and reloads the
proxy lives in ``deployers/waf.py``.

All times are naive UTC: timestamps parsed from the audit stream are normalized
to naive UTC, and callers pass a naive-UTC ``now`` — so comparisons (and the DB's
``DateTime`` column) never mix aware/naive values.
"""

from __future__ import annotations

import ipaddress
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(spec: str) -> timedelta:
    """Parse a ``[waf.bans]`` duration (``"30s"``/``"10m"``/``"1h"``/``"7d"``).

    The schema validates the format (``^[1-9]\\d*[smhd]$``), so this assumes it.
    """
    return timedelta(seconds=int(spec[:-1]) * _UNIT_SECONDS[spec[-1]])


def utcnow() -> datetime:
    """Current time as naive UTC (the convention used throughout ban handling)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_ts(value: object) -> datetime | None:
    """Parse an ISO-8601 audit timestamp to naive UTC, or None if unparseable."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def is_exempt(ip: str, exempt_cidrs: Iterable[str]) -> bool:
    """True if ``ip`` falls in any exempt CIDR (Security invariant 5).

    Operator-registered networks (office/VPN/monitors) are never banned — they
    double as the exemption list so a bad allowlist can't lock out trusted users.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in exempt_cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def sources_to_ban(
    entries: Iterable[Mapping],
    *,
    threshold: int,
    window: timedelta,
    now: datetime,
    exempt_cidrs: Iterable[str] = (),
) -> dict[str, int]:
    """Sources with ``>= threshold`` ``blocked`` events within ``window``.

    Args:
        entries: parsed audit records (dicts with ``action``/``client_ip``/
            ``timestamp``).
        threshold: violations within the window that trip a ban.
        window: the scoring window (look back ``now - window``).
        now: naive-UTC reference time.
        exempt_cidrs: CIDRs whose IPs are never banned (invariant 5).

    Returns:
        ``{source_ip: violation_count}`` for sources over the threshold.
    """
    cutoff = now - window
    exempt = tuple(exempt_cidrs)
    counts: Counter[str] = Counter()
    for entry in entries:
        if entry.get("action") != "blocked":
            continue
        ip = entry.get("client_ip")
        if not ip or is_exempt(ip, exempt):
            continue
        when = _parse_ts(entry.get("timestamp"))
        if when is None or when < cutoff:
            continue
        counts[ip] += 1
    return {ip: count for ip, count in counts.items() if count >= threshold}
