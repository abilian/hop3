# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Host-wide registry of fixed ports claimed by apps.

Non-HTTP services (SMTP, XMPP, RTMP, Matrix federation, …) bind a host port
directly — there is no reverse proxy or virtual hosting for them, so exactly
one app can own a given ``(number, protocol)`` on the host. Each declared
``[[ports]]`` entry becomes a :class:`PortClaim`; the unique constraint makes a
conflicting second app fail fast (the deployer turns that into a clear pre-flight
error), and ``rule_id`` records the firewall rule so teardown can close it.
"""

from __future__ import annotations

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import App


class PortClaim(BigIntAuditBase):
    """One fixed host port (TCP or UDP) claimed exclusively by an app."""

    __tablename__ = "port_claim"

    app_id: Mapped[int] = mapped_column(
        ForeignKey(App.id, ondelete="CASCADE"), nullable=False
    )
    # Port number (1-65535), validated upstream by the schema.
    number: Mapped[int] = mapped_column(nullable=False)
    protocol: Mapped[str] = mapped_column(String(3), default="tcp", nullable=False)
    # App name at claim time — kept for diagnostics even if the app row is gone.
    app_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Who may reach the port: "any" (default) or an IPv4 CIDR. Passed to rootd
    # when the firewall rule is opened; stored so teardown/reconcile and the
    # `hop3 ports` listing know the declared scope.
    source: Mapped[str] = mapped_column(String(64), default="any", nullable=False)
    # rootd firewall rule id, set once the port is opened; used to close it on
    # teardown. None when the firewall could not be reached (claim still holds).
    rule_id: Mapped[str | None] = mapped_column(String(64), default=None)

    app: Mapped[App] = relationship(back_populates="port_claims")

    __table_args__ = (
        UniqueConstraint("number", "protocol", name="uq_port_claim_number_protocol"),
    )
