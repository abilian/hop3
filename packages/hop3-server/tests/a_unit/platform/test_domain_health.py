# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Domain registration (WHOIS) + DNS health probing.

check_domain is best-effort and must never raise: WHOIS/DNS failures degrade to
"unknown" with a note, never an exception.
"""

from __future__ import annotations

import datetime
import socket
from types import SimpleNamespace

from hop3.platform import domain_health
from hop3.platform.domain_health import (
    DomainHealth,
    all_domain_health,
    check_domain,
    get_domain_health,
    set_domain_health,
)

NOW = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


def _dt(year: int, month: int, day: int) -> datetime.datetime:
    return datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)


def _addrinfo(*ips):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]


def _whois(monkeypatch, *, expiry=None, raises=False):
    def fake(_domain):
        if raises:
            msg = "rate limited"
            raise RuntimeError(msg)
        return SimpleNamespace(expiration_date=expiry)

    monkeypatch.setattr(domain_health.whois, "whois", fake)


def _dns(monkeypatch, *ips, raises=False):
    def fake(*_a, **_k):
        if raises:
            msg = "nxdomain"
            raise OSError(msg)
        return _addrinfo(*ips)

    monkeypatch.setattr(domain_health.socket, "getaddrinfo", fake)


def test_healthy_domain(monkeypatch):
    _whois(monkeypatch, expiry=_dt(2026, 6, 1))
    _dns(monkeypatch, "203.0.113.5")
    h = check_domain("edrix.eu", server_ips=frozenset({"203.0.113.5"}), now=NOW)
    assert h.registration_expiry == datetime.date(2026, 6, 1)
    assert h.registration_days_left == 151
    assert h.resolves is True
    assert h.points_here is True
    assert h.resolved_ips == ("203.0.113.5",)
    assert h.notes == ()


def test_dns_points_elsewhere(monkeypatch):
    _whois(monkeypatch, expiry=_dt(2027, 1, 1))
    _dns(monkeypatch, "198.51.100.9")
    h = check_domain("edrix.eu", server_ips=frozenset({"203.0.113.5"}), now=NOW)
    assert h.points_here is False
    assert any("not this server" in n for n in h.notes)


def test_whois_failure_is_unknown_not_fatal(monkeypatch):
    _whois(monkeypatch, raises=True)
    _dns(monkeypatch, "203.0.113.5")
    h = check_domain("edrix.eu", server_ips=frozenset({"203.0.113.5"}), now=NOW)
    assert h.registration_expiry is None
    assert any("WHOIS" in n for n in h.notes)
    assert h.resolves is True  # DNS still probed


def test_no_dns(monkeypatch):
    _whois(monkeypatch, expiry=_dt(2027, 1, 1))
    _dns(monkeypatch, raises=True)
    h = check_domain("edrix.eu", now=NOW)
    assert h.resolves is False
    assert h.points_here is None
    assert any("does not resolve" in n for n in h.notes)


def test_expired_registration(monkeypatch):
    _whois(monkeypatch, expiry=_dt(2025, 12, 1))
    _dns(monkeypatch, "203.0.113.5")
    h = check_domain("edrix.eu", server_ips=frozenset({"203.0.113.5"}), now=NOW)
    assert h.registration_days_left == -31
    assert any("expired" in n for n in h.notes)


def test_expiration_date_list_takes_first(monkeypatch):
    _whois(
        monkeypatch,
        expiry=[_dt(2026, 6, 1), _dt(2027, 1, 1)],
    )
    _dns(monkeypatch, "203.0.113.5")
    h = check_domain("edrix.eu", now=NOW)
    assert h.registration_expiry == datetime.date(2026, 6, 1)


def test_private_server_ip_makes_points_here_unknown(monkeypatch):
    _whois(monkeypatch, expiry=_dt(2027, 1, 1))
    _dns(monkeypatch, "203.0.113.5")
    h = check_domain("edrix.eu", server_ips=frozenset({"10.0.0.5"}), now=NOW)
    assert h.points_here is None  # private/NAT IP can't be compared reliably


def test_snapshot_store_roundtrip():
    health = DomainHealth(domain="x.example.com")
    set_domain_health({"x.example.com": health})
    try:
        assert get_domain_health("x.example.com") is health
        assert all_domain_health() == {"x.example.com": health}
        assert get_domain_health("absent.example.com") is None
    finally:
        set_domain_health({})
