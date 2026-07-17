# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""ORM model for an app's initial admin credential (ADR 056)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from hop3.orm import App


class AppAdminCredential(BigIntAuditBase):
    """The initial admin account Hop3 bootstrapped for an app (ADR 056).

    Holds the username, email, and password Hop3 generated when it created the
    app's first admin account, so the operator can retrieve or reset it later
    instead of catching a one-shot deploy-log print. The whole triple is stored
    as one Fernet-encrypted JSON blob (keyed from HOP3_SECRET_KEY), mirroring
    ``AddonCredential``; ``created_at`` comes from ``BigIntAuditBase``.

    This is the credential Hop3 *set*. If the user later changes it inside the
    app, the stored value is stale — callers must present it as the INITIAL
    credential and point at ``hop3 app admin-reset`` for a known password.

    One per app (unique on ``app_id``); cascade-deletes with the app.
    """

    __tablename__ = "app_admin_credential"

    app_id: Mapped[int] = mapped_column(
        ForeignKey("app.id", ondelete="CASCADE"), nullable=False
    )

    encrypted_data: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="Fernet-encrypted JSON: {username, email, password}",
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="generated",
        comment="How the credential was set: 'generated' (install) or 'reset'.",
    )

    # Run-once guard for the post-deploy `[admin].create` step: set True once the
    # account has actually been created, so a redeploy doesn't re-run bootstrap.
    bootstrapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Show-once guard for the deploy-log credential block: set True the first time
    # the credential is surfaced, so it is never re-printed on a later redeploy.
    surfaced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    app: Mapped[App] = relationship(back_populates="admin_credential")

    __table_args__ = (UniqueConstraint("app_id", name="uq_app_admin_credential_app"),)

    def __repr__(self) -> str:
        return f"<AppAdminCredential(app_id={self.app_id}, source={self.source})>"
