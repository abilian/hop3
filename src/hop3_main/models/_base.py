# Copyright (c) 2019-2024, Abilian SAS - All rights reserved

# ruff: noqa: N805
from __future__ import annotations

import typing
from datetime import datetime, timezone

from advanced_alchemy.base import (
    AuditColumns,
    BigIntPrimaryKey,
    CommonTableAttributes,
    orm_registry,
)
from advanced_alchemy.repository import SQLAlchemySyncRepository
from advanced_alchemy.service import SQLAlchemySyncRepositoryService
from advanced_alchemy.types import BigIntIdentity, DateTimeUTC
from sqlalchemy import ForeignKey
from sqlalchemy.orm import (
    DeclarativeBase,
    declared_attr,
    Mapped,
    mapped_column,
    relationship,
)

if typing.TYPE_CHECKING:
    from .auth import User


class Owned:
    # owner_id: Mapped[int] = mapped_column(BigIntIdentity, ForeignKey("user.id"), nullable=True)
    # owner: Mapped[User] = relationship("User")

    @declared_attr
    def owner_id(_cls) -> Mapped[int]:
        from .auth import User

        return mapped_column(BigIntIdentity, ForeignKey(User.id), nullable=True)

    @declared_attr
    def owner(_cls) -> Mapped[User]:
        from .auth import User

        return relationship(User, foreign_keys=[_cls.owner_id])  # type: ignore


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        # TEMP
        nullable=True,
    )
    """Date/time of instance creation."""


class Base(CommonTableAttributes, BigIntPrimaryKey, DeclarativeBase):
    registry = orm_registry


class AuditBase(CommonTableAttributes, BigIntPrimaryKey, AuditColumns, DeclarativeBase):
    """Base for declarative models with BigInt primary keys and audit
    columns."""

    registry = orm_registry

    created_at: Mapped[datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        # TEMP
        nullable=True,
    )
    """Date/time of instance creation."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        # TEMP
        nullable=True,
    )
    """Date/time of instance last update."""


class TimestampedBase(
    CommonTableAttributes, BigIntPrimaryKey, Timestamped, DeclarativeBase
):
    """Base for immutable declarative models with BigInt primary keys and
    timestamp."""

    registry = orm_registry


Repository = SQLAlchemySyncRepository

RepositoryService = SQLAlchemySyncRepositoryService
