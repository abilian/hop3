# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""L7 ban scoring (ADR 050 §4) — pure logic over the audit stream."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from hop3.waf.bans import is_exempt, parse_duration, sources_to_ban

# Naive UTC by design — ban scoring normalizes everything to naive UTC.
NOW = datetime(2026, 6, 25, 12, 0, 0)  # ruff:ignore[call-datetime-without-tzinfo]


def _blocked(ip: str, when: datetime, action: str = "blocked") -> dict:
    return {"action": action, "client_ip": ip, "timestamp": when.isoformat()}


def test_parse_duration_units():
    assert parse_duration("30s") == timedelta(seconds=30)
    assert parse_duration("10m") == timedelta(minutes=10)
    assert parse_duration("2h") == timedelta(hours=2)
    assert parse_duration("7d") == timedelta(days=7)


def test_is_exempt_matches_cidr():
    assert is_exempt("203.0.113.9", ["203.0.113.0/24"])
    assert not is_exempt("198.51.100.1", ["203.0.113.0/24"])
    assert not is_exempt("not-an-ip", ["203.0.113.0/24"])


def test_bans_source_over_threshold_in_window():
    entries = [_blocked("1.2.3.4", NOW - timedelta(minutes=i)) for i in range(5)]
    result = sources_to_ban(entries, threshold=5, window=timedelta(minutes=10), now=NOW)
    assert result == {"1.2.3.4": 5}


def test_under_threshold_is_not_banned():
    entries = [_blocked("1.2.3.4", NOW - timedelta(minutes=i)) for i in range(4)]
    result = sources_to_ban(entries, threshold=5, window=timedelta(minutes=10), now=NOW)
    assert result == {}


def test_events_outside_window_do_not_count():
    entries = [
        _blocked("1.2.3.4", NOW - timedelta(minutes=1)),
        _blocked("1.2.3.4", NOW - timedelta(minutes=2)),
        *[_blocked("1.2.3.4", NOW - timedelta(minutes=30)) for _ in range(5)],  # stale
    ]
    result = sources_to_ban(entries, threshold=5, window=timedelta(minutes=10), now=NOW)
    assert result == {}  # only 2 recent < threshold 5


def test_allowed_events_are_ignored():
    entries = [_blocked("1.2.3.4", NOW, action="allowed") for _ in range(9)]
    assert (
        sources_to_ban(entries, threshold=5, window=timedelta(minutes=10), now=NOW)
        == {}
    )


def test_exempt_network_is_never_banned():
    """Security invariant 5: trusted networks double as the exemption list."""
    entries = [_blocked("203.0.113.7", NOW - timedelta(seconds=i)) for i in range(20)]
    result = sources_to_ban(
        entries,
        threshold=5,
        window=timedelta(minutes=10),
        now=NOW,
        exempt_cidrs=["203.0.113.0/24"],
    )
    assert result == {}


def test_malformed_timestamps_are_skipped():
    entries = [{"action": "blocked", "client_ip": "1.2.3.4", "timestamp": "nope"}]
    assert (
        sources_to_ban(entries, threshold=1, window=timedelta(minutes=10), now=NOW)
        == {}
    )


def test_aware_timestamps_are_normalized():
    """Audit timestamps are tz-aware UTC; scoring must compare cleanly."""
    entries = [
        {
            "action": "blocked",
            "client_ip": "1.2.3.4",
            "timestamp": (NOW - timedelta(minutes=1)).isoformat() + "+00:00",
        }
        for _ in range(5)
    ]
    result = sources_to_ban(entries, threshold=5, window=timedelta(minutes=10), now=NOW)
    assert result == {"1.2.3.4": 5}


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
