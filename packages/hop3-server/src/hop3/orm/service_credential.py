# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""ORM model for encrypted service credentials."""

from __future__ import annotations

from typing import TYPE_CHECKING

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from hop3.orm import App


class ServiceCredential(BigIntAuditBase):
    """Encrypted storage for service credentials.

    Stores connection details and authentication credentials for attached
    services (PostgreSQL, Redis, S3, etc.). Credentials are encrypted at
    rest using Fernet symmetric encryption derived from HOP3_SECRET_KEY.

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

    __tablename__ = "service_credential"

    # Foreign key to app (cascade delete)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("app.id", ondelete="CASCADE"), nullable=False
    )

    # Service identification
    service_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Service type: postgresql, redis, s3, etc.",
    )
    service_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="User-provided service instance name"
    )

    # Encrypted credentials (JSON blob)
    encrypted_data: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="Fernet-encrypted JSON containing credentials",
    )

    # Relationships
    app: Mapped[App] = relationship(back_populates="service_credentials")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "app_id",
            "service_type",
            "service_name",
            name="uq_service_credential_app_service",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ServiceCredential(app_id={self.app_id}, "
            f"type={self.service_type}, name={self.service_name})>"
        )
