# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard certificates / TLS health controller."""

from __future__ import annotations

from litestar import Controller, get
from litestar.response import Template

from hop3.orm import AppRepository
from hop3.platform.cert_health import cert_health
from hop3.platform.domain_health import DomainHealth, all_domain_health
from hop3.platform.health_alerts import collect_alerts
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session


class CertificatesController(Controller):
    """Read-only TLS + domain health for every app's domain."""

    path = "/dashboard/certificates"
    guards = [auth_guard]  # ruff:ignore[mutable-class-default]

    @get("/", sync_to_thread=False)
    def dashboard_certificates(self) -> Template:
        """Display per-app cert + domain/DNS health, with a problem banner."""
        with get_session() as db_session:
            certs = cert_health(AppRepository(session=db_session).list_all_ordered())

        domains = all_domain_health()
        alerts = collect_alerts(certs, domains)
        rows = [
            {
                "app_name": c.app_name,
                "domain": c.domain,
                "kind": c.kind,
                "days_left": c.days_left,
                "status": c.status,
                "reg_days_left": _reg_days(domains.get(c.domain)),
                "dns": _dns_label(domains.get(c.domain)),
            }
            for c in certs
        ]
        return Template(
            template_name="dashboard/certificates.html",
            context={
                "rows": rows,
                "alerts": [{"level": a.level, "message": a.message} for a in alerts],
            },
        )


def _reg_days(dh: DomainHealth | None) -> int | None:
    return dh.registration_days_left if dh else None


def _dns_label(dh: DomainHealth | None) -> str:
    """Short DNS status; '—' until the daily collector has run for the domain."""
    if dh is None:
        return "—"
    if dh.resolves is False:
        return "no DNS"
    if dh.points_here is False:
        return "elsewhere"
    if dh.points_here is True:
        return "ok"
    return "resolves"
