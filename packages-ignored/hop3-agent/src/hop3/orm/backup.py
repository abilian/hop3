# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from enum import Enum

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from . import App


class BackupStateEnum(Enum):
    """Enumeration representing the various states of a backup process.

    The backup process can be in one of the following states:

    - SCHEDULED: Indicates the backup is scheduled and yet to start.
    - STARTED: Indicates the backup process has started.
    - COMPLETED: Indicates the backup has completed successfully.
    - FAILED: Indicates the backup process has failed.
    """

    SCHEDULED = 1
    STARTED = 2
    COMPLETED = 3
    FAILED = 4


class Backup(BigIntAuditBase):
    """Represents a backup entry in the database, extending from the
    BigIntAuditBase class.

    This defines the database schema for storing information about
    backups, including their state, format, remote path, size, and
    expiry time.
    """

    __tablename__ = "backup"

    app_id: Mapped[int] = mapped_column(ForeignKey(App.id))

    state: Mapped[BackupStateEnum] = mapped_column(default=BackupStateEnum.SCHEDULED)
    format: Mapped[str] = mapped_column(default="tgz")
    remote_path: Mapped[str] = mapped_column(unique=True)
    size: Mapped[int] = mapped_column(default=0)

    # Time to keep backups in seconds / never expires by default
    expires_after: Mapped[int] = mapped_column(default=0)

    # TODO: encryption
