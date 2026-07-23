# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Per-app TLS certificate health (type, days to expiry, status).

Shared by ``hop3 cert status`` and the dashboard health page so both report
identical data. Pure read-only inspection of the stored certs — no issuance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3.platform.cert_renewal import app_cert_domain
from hop3.platform.certificates import Certificate

if TYPE_CHECKING:
    from hop3.orm import App

# Renewal fires at 30 days; if a cert drops below this, renewal has demonstrably
# failed to keep it fresh, so the dashboard flags it as a warning worth acting on.
EXPIRY_WARNING_DAYS = 14


@dataclass(frozen=True)
class CertHealth:
    app_name: str
    domain: str
    kind: str  # "CA" | "self-signed" | "missing"
    days_left: int | None
    status: str  # "ok" | "expiring" | "expired" | "missing"


def cert_status(days_left: int | None, *, exists: bool) -> str:
    """Classify a cert by its remaining validity."""
    if not exists or days_left is None:
        return "missing"
    if days_left < 0:
        return "expired"
    if days_left < EXPIRY_WARNING_DAYS:
        return "expiring"
    return "ok"


def cert_health(apps: list[App]) -> list[CertHealth]:
    """Health row per app that has a managed (non-catch-all) domain."""
    out: list[CertHealth] = []
    for app in apps:
        domain = app_cert_domain(app)
        if not domain:
            continue
        cert = Certificate(domain_name=domain)
        exists = cert.crt_file.exists()
        days = cert.days_until_expiry()
        if not exists:
            kind = "missing"
        elif cert.is_self_signed():
            kind = "self-signed"
        else:
            kind = "CA"
        out.append(
            CertHealth(
                app_name=app.name,
                domain=domain,
                kind=kind,
                days_left=days,
                status=cert_status(days, exists=exists),
            )
        )
    return out
