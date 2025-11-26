# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""ORM model for encrypted addon credentials."""

from __future__ import annotations

from typing import TYPE_CHECKING

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from hop3.orm import App


class AddonCredential(BigIntAuditBase):
    """Encrypted storage for addon credentials.

    Stores connection details and authentication credentials for attached
    addons (PostgreSQL, Redis, S3, etc.). Addons are backing services in
    12-factor app terminology. Credentials are encrypted at rest using
    Fernet symmetric encryption derived from HOP3_SECRET_KEY.

    Examples:
        PostgreSQL credentials:
            {
                "username": "myapp_db",
                "password": "xyz...",
                "database": "myapp_db",
                "host": "localhost",
                "port": 5432
            }

        Redis credentials:
            {
                "host": "localhost",
                "port": 6379,
                "password": "abc...",
                "db": 0
            }
    """

    __tablename__ = "addon_credential"

    # Foreign key to app (cascade delete)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("app.id", ondelete="CASCADE"), nullable=False
    )

    # Addon identification
    addon_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Addon type: postgresql, redis, s3, etc.",
    )
    addon_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="User-provided addon instance name"
    )

    # Encrypted credentials (JSON blob)
    encrypted_data: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="Fernet-encrypted JSON containing credentials",
    )

    # Relationships
    app: Mapped[App] = relationship(back_populates="addon_credentials")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "app_id",
            "addon_type",
            "addon_name",
            name="uq_addon_credential_app_addon",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AddonCredential(app_id={self.app_id}, "
            f"type={self.addon_type}, name={self.addon_name})>"
        )
