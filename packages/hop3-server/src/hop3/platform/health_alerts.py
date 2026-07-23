# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Aggregate cert + domain health into dashboard alert banners.

A first, simple step toward a fuller alerting framework: turn the cert and
domain-health snapshots into a flat, severity-ordered list of human-readable
problems for the dashboard banner. Pure function over the health models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3.platform.domain_health import REGISTRATION_WARNING_DAYS

if TYPE_CHECKING:
    from hop3.platform.cert_health import CertHealth
    from hop3.platform.domain_health import DomainHealth

CRITICAL = "critical"
WARNING = "warning"


@dataclass(frozen=True)
class Alert:
    level: str  # CRITICAL | WARNING
    message: str


def collect_alerts(
    certs: list[CertHealth], domains: dict[str, DomainHealth]
) -> list[Alert]:
    """Flatten cert + domain health into alerts, criticals first."""
    critical: list[Alert] = []
    warning: list[Alert] = []

    for c in certs:
        if c.status == "expired":
            critical.append(
                Alert(CRITICAL, f"{c.app_name}: TLS certificate for {c.domain} expired")
            )
        elif c.status == "missing":
            warning.append(
                Alert(WARNING, f"{c.app_name}: no TLS certificate for {c.domain}")
            )
        elif c.status == "expiring":
            warning.append(
                Alert(
                    WARNING,
                    f"{c.app_name}: TLS certificate for {c.domain} "
                    f"expires in {c.days_left}d",
                )
            )

        dh = domains.get(c.domain)
        if dh is None:
            continue
        days = dh.registration_days_left
        if days is not None and days < 0:
            critical.append(Alert(CRITICAL, f"{c.domain}: domain registration expired"))
        elif days is not None and days < REGISTRATION_WARNING_DAYS:
            warning.append(
                Alert(WARNING, f"{c.domain}: domain registration expires in {days}d")
            )
        if dh.resolves is False:
            critical.append(Alert(CRITICAL, f"{c.domain}: does not resolve in DNS"))
        elif dh.points_here is False:
            ips = ", ".join(dh.resolved_ips)
            warning.append(Alert(WARNING, f"{c.domain}: DNS points elsewhere ({ips})"))

    return critical + warning
