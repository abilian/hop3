# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Host-wide registry of fixed ports claimed by apps *and* exposed addons.

Non-HTTP services (SMTP, XMPP, RTMP, Matrix federation, …) bind a host port
directly — there is no reverse proxy or virtual hosting for them, so exactly
one owner can hold a given ``(number, protocol)`` on the host. Each declared
``[[ports]]`` entry becomes a :class:`PortClaim`; the unique constraint makes a
conflicting second owner fail fast (the deployer turns that into a clear
pre-flight error), and ``rule_id`` records the firewall rule so teardown can
close it.

Two kinds of claim share the one host-wide port space (so app fixed-ports and
addon exposures can never collide):

- **app claim** — ``app_id`` + ``app_name`` set, ``addon_*`` null.
- **addon-exposure claim** (``hop3 addon expose``) — ``app_id`` null,
  ``addon_type`` + ``addon_name`` set, ``proxy_unit`` records the
  systemd-socket-proxyd forwarder and ``source`` the access scope. ``app_name``
  carries the firewall tag so the ``list_rules`` orphan-sweep still works.
"""

from __future__ import annotations

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import App


class PortClaim(BigIntAuditBase):
    """One fixed host port (TCP or UDP) claimed by an app or an exposed addon."""

    __tablename__ = "port_claim"

    # Null for an addon-exposure claim (an exposed addon is not owned by an App).
    app_id: Mapped[int | None] = mapped_column(
        ForeignKey(App.id, ondelete="CASCADE"), nullable=True
    )
    # Port number (1-65535), validated upstream by the schema.
    number: Mapped[int] = mapped_column(nullable=False)
    protocol: Mapped[str] = mapped_column(String(3), default="tcp", nullable=False)
    # Owner tag at claim time (app name, or the firewall tag for an exposure) —
    # kept for diagnostics and the firewall list_rules orphan-sweep.
    app_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Who may reach the port: "any" (default) or an IPv4 CIDR. Applies to both an
    # app fixed-port claim and an addon exposure. Passed to rootd when the
    # firewall rule is opened; stored so teardown/reconcile and the `hop3 ports`
    # listing know the declared scope.
    source: Mapped[str] = mapped_column(String(64), default="any", nullable=False)
    # rootd firewall rule id, set once the port is opened; used to close it on
    # teardown. None when the firewall could not be reached (claim still holds).
    rule_id: Mapped[str | None] = mapped_column(String(64), default=None)

    # Addon-exposure fields (null for an app fixed-port claim).
    addon_type: Mapped[str | None] = mapped_column(String(32), default=None)
    addon_name: Mapped[str | None] = mapped_column(String(128), default=None)
    # systemd-socket-proxyd unit base name backing the exposure (for teardown).
    proxy_unit: Mapped[str | None] = mapped_column(String(128), default=None)

    app: Mapped[App | None] = relationship(back_populates="port_claims")

    __table_args__ = (
        UniqueConstraint("number", "protocol", name="uq_port_claim_number_protocol"),
    )
