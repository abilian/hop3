# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Renew TLS certificates that are due and reinstall them into the proxy.

Shared by the ``hop3 cert renew`` RPC command and the unattended renewal timer so
both apply identical logic. A per-app failure is recorded and does not stop the
others; the caller decides how to surface the collected failures (the command
returns them as errors, the timer logs them) — they are never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hop3.config import NGINX_ROOT
from hop3.platform.certificates import (
    Certificate,
    CertificatesManager,
    verify_cert,
    write_private_key,
)

if TYPE_CHECKING:
    from hop3.orm import App


@dataclass(frozen=True)
class RenewOutcome:
    renewed: list[str] = field(default_factory=list)  # "app (domain)"
    failed: list[tuple[str, str]] = field(default_factory=list)  # (label, error)
    checked: int = 0


def app_cert_domain(app: App) -> str | None:
    """The cert domain for an app: the first host of HOST_NAME.

    None when the app has no HOST_NAME or uses the catch-all "_" (no managed
    public certificate to renew).
    """
    for env_var in app.env_vars:
        if env_var.name == "HOST_NAME":
            hosts = env_var.value.split()
            if hosts and hosts[0] != "_":
                return hosts[0]
            return None
    return None


def install_cert_to_nginx(app_name: str, domain_name: str) -> None:
    """Copy a freshly issued cert into the proxy's per-app files."""
    cert = Certificate(domain_name=domain_name)
    (NGINX_ROOT / f"{app_name}.crt").write_text(cert.get_crt())
    write_private_key(NGINX_ROOT / f"{app_name}.key", cert.get_key())


def renew_due_certs(
    apps: list[App],
    *,
    threshold_days: int = 30,
    force: bool = False,
    manager: CertificatesManager | None = None,
) -> RenewOutcome:
    """Renew each app's cert that is due (or all, with ``force``) and reinstall it.

    Does not reload the proxy — the caller reloads once if anything was renewed.
    """
    manager = manager or CertificatesManager()
    renewed: list[str] = []
    failed: list[tuple[str, str]] = []
    checked = 0
    for app in apps:
        domain = app_cert_domain(app)
        if not domain:
            continue
        if not Certificate(domain_name=domain).crt_file.exists():
            # hop3 doesn't manage this app's cert (e.g. the proxy runs its own
            # auto-HTTPS); renewing here would spuriously issue an unused cert.
            continue
        checked += 1
        label = f"{app.name} ({domain})"
        try:
            changed = manager.renew(domain, threshold_days=threshold_days, force=force)
            if changed:
                install_cert_to_nginx(app.name, domain)
                verify_cert(domain)  # post-condition; a bad renewal counts as failed
                renewed.append(label)
        except Exception as e:
            # Collect per-app failures instead of aborting the batch; the caller
            # surfaces them (command -> error, service -> log). Never dropped.
            failed.append((label, str(e)))
            continue
    return RenewOutcome(renewed=renewed, failed=failed, checked=checked)
