# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""L7 WAF bans — per-app, time-limited source denials (ADR 050 §4 / §8).

A repeated attacker (allow-misses, gate-fails, CRS hits) is cut off once instead
of re-inspecting every request. The ban scorer consumes the WAF audit stream and
records a :class:`Ban` per offending source; the engine compiles active bans into
a denylist the proxy enforces. Bans are runtime state (DB), managed via
``hop3 waf bans`` (and, later, the admin UI), and are app-scoped: each app's
proxy holds its own denylist.
"""

from __future__ import annotations

from datetime import datetime

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import App


class Ban(BigIntAuditBase):
    """A time-limited denial of one source IP for one app."""

    __tablename__ = "ban"

    app_id: Mapped[int] = mapped_column(
        ForeignKey(App.id, ondelete="CASCADE"), nullable=False
    )
    # Kept for diagnostics / CLI listing without a join.
    app_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # The banned source IP (the trusted client IP from the audit stream).
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    # Why it was banned (e.g. "8 violations in 10m"), surfaced to the operator.
    reason: Mapped[str] = mapped_column(String(256), default="")
    # When the ban lifts; the scorer drops elapsed bans and stops enforcing them.
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    app: Mapped[App] = relationship()

    # One active ban row per (app, source); a re-ban updates expires_at in place.
    __table_args__ = (UniqueConstraint("app_id", "source", name="uq_ban_app_source"),)
