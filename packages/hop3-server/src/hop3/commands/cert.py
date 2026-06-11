# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""``hop3 cert`` — inspect and renew TLS certificates.

``hop3 cert status`` lists each app's certificate (type, days to expiry).
``hop3 cert renew`` re-issues certs due within ``--days`` (default 30) or all
with ``--force``, reinstalls them into nginx, and reloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.lib.args import parse_cli_args
from hop3.lib.registry import register
from hop3.orm.repositories import AppRepository
from hop3.platform.cert_health import cert_health
from hop3.platform.cert_renewal import renew_due_certs
from hop3.platform.certificates import reload_nginx

from ._base import Command
from ._response import error, table, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.platform.cert_renewal import RenewOutcome


@register
class CertCmd(Command):
    """Inspect and renew TLS certificates."""

    name: ClassVar[tuple[str, ...]] = ("cert",)


@register
@dataclass(frozen=True)
class CertStatusCmd(Command):
    """Show each app's TLS certificate: type, days to expiry, status.

    Example:
        hop3 cert status
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("cert", "status")

    def call(self, *args):
        apps = AppRepository(session=self.db_session).list_all_ordered()
        rows = [
            [
                h.app_name,
                h.domain,
                h.kind,
                "-" if h.days_left is None else str(h.days_left),
                h.status,
            ]
            for h in cert_health(apps)
        ]
        if not rows:
            return [text("No apps have a managed TLS certificate.")]
        return [
            table(
                headers=["app", "domain", "type", "days left", "status"],
                rows=rows,
            )
        ]


@register
@dataclass(frozen=True)
class CertRenewCmd(Command):
    """Renew certs due within --days (default 30), or all with --force.

    Examples:
        hop3 cert renew
        hop3 cert renew myapp
        hop3 cert renew --force
        hop3 cert renew --days 45
    """

    db_session: Session
    name: ClassVar[tuple[str, ...]] = ("cert", "renew")
    _arg_spec: ClassVar[dict] = {
        "app": {"positional": True},
        "force": {"flag": True},
        "days": {"type": int, "default": 30},
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        only_app = parsed.get("app")
        force = bool(parsed.get("force"))
        threshold = parsed.get("days", 30)

        apps = AppRepository(session=self.db_session).list_all_ordered()
        if only_app:
            apps = [a for a in apps if a.name == only_app]
            if not apps:
                return [error(f"App not found: {only_app}")]

        outcome = renew_due_certs(apps, threshold_days=threshold, force=force)
        if outcome.renewed:
            reload_nginx()
        return _render(outcome)


def _render(outcome: RenewOutcome) -> list[dict]:
    out: list[dict] = []
    if outcome.renewed:
        out.append(text("Renewed:\n  " + "\n  ".join(outcome.renewed)))
    if outcome.failed:
        out.append(
            error(
                "Failed:\n  "
                + "\n  ".join(f"{label}: {err}" for label, err in outcome.failed)
            )
        )
    if not outcome.renewed and not outcome.failed:
        out.append(
            text(f"No certificates due for renewal ({outcome.checked} checked).")
        )
    return out
