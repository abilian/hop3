# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from enum import Enum

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_serializer import SerializerMixin

from .instance import Instance


class BackupStateEnum(Enum):
    SCHEDULED = 1
    STARTED = 2
    COMPLETED = 3
    FAILED = 4


class Backup(BigIntAuditBase, SerializerMixin):
    __tablename__ = "backup"

    instance_id: Mapped[int] = mapped_column(ForeignKey(Instance.id))

    state: Mapped[BackupStateEnum] = mapped_column(default=BackupStateEnum.SCHEDULED)
    format: Mapped[str] = mapped_column(default="tgz")
    remote_path: Mapped[str] = mapped_column(unique=True)
    size: Mapped[int] = mapped_column(default=0)

    # Time to keep backups in seconds / never expires by default
    expires_after: Mapped[int] = mapped_column(default=0)

    # TODO: encryption

    # JSON data
    # manifest_json: Mapped = mapped_column(JSON)
