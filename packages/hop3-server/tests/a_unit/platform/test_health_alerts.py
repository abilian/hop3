# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Dashboard alert aggregation from cert + domain health."""

from __future__ import annotations

from hop3.platform.cert_health import CertHealth
from hop3.platform.domain_health import DomainHealth
from hop3.platform.health_alerts import collect_alerts


def _cert(app, domain, status, days_left=None, kind="CA"):
    return CertHealth(
        app_name=app, domain=domain, kind=kind, days_left=days_left, status=status
    )


def test_no_alerts_for_healthy():
    certs = [_cert("a", "a.example.com", "ok", days_left=80)]
    domains = {
        "a.example.com": DomainHealth(
            domain="a.example.com",
            registration_days_left=300,
            resolves=True,
            points_here=True,
        )
    }
    assert collect_alerts(certs, domains) == []


def test_cert_states():
    certs = [
        _cert("a", "a.example.com", "expired"),
        _cert("b", "b.example.com", "expiring", days_left=5),
        _cert("c", "c.example.com", "missing"),
    ]
    msgs = [a.message for a in collect_alerts(certs, {})]
    assert any("a.example.com expired" in m for m in msgs)
    assert any("expires in 5d" in m for m in msgs)
    assert any("no TLS certificate for c.example.com" in m for m in msgs)


def test_domain_and_dns_alerts():
    certs = [_cert("a", "a.example.com", "ok", days_left=80)]
    domains = {
        "a.example.com": DomainHealth(
            domain="a.example.com",
            registration_days_left=-3,
            resolves=True,
            points_here=False,
            resolved_ips=("198.51.100.1",),
        )
    }
    msgs = [a.message for a in collect_alerts(certs, domains)]
    assert any("domain registration expired" in m for m in msgs)
    assert any("DNS points elsewhere (198.51.100.1)" in m for m in msgs)


def test_criticals_sort_before_warnings():
    certs = [
        _cert("warn", "w.example.com", "expiring", days_left=10),
        _cert("crit", "c.example.com", "expired"),
    ]
    alerts = collect_alerts(certs, {})
    assert alerts[0].level == "critical"
    assert alerts[-1].level == "warning"
