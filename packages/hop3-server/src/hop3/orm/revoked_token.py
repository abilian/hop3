# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Revoked JWT token tracking.

This module provides a revocation list (denylist) for JWT tokens.
When a user logs out or a token needs to be invalidated, its JTI
(JWT ID) is added to this list. The authentication middleware checks
this list to reject revoked tokens even if they haven't expired yet.
"""

from __future__ import annotations

from datetime import datetime, timezone

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy.orm import Mapped, mapped_column


class RevokedToken(BigIntAuditBase):
    """Model for tracking revoked JWT tokens.

    Attributes:
        jti: JWT ID (unique token identifier from the 'jti' claim)
        revoked_at: Timestamp when the token was revoked
        expires_at: When the token would have expired naturally (for cleanup)
        reason: Optional reason for revocation (e.g., "user_logout", "security_breach")
    """

    __tablename__ = "revoked_token"

    # JWT ID (from 'jti' claim) - unique identifier for the token
    jti: Mapped[str] = mapped_column(unique=True, index=True)

    # Timestamp when the token was revoked
    revoked_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    # When the token expires (for cleanup - can delete old entries after this)
    expires_at: Mapped[datetime]

    # Optional reason for revocation
    reason: Mapped[str | None] = mapped_column(default=None)

    def __repr__(self) -> str:
        """String representation."""
        return f"<RevokedToken(jti={self.jti!r}, revoked_at={self.revoked_at})>"
