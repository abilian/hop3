# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from enum import Enum

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from hop3.model.app import App


class InstanceStateEnum(Enum):
    """
    Enumeration representing the state of an instance.
    """

    RUNNING = 1
    STOPPED = 2
    PAUSED = 3
    # ...


class Instance(BigIntAuditBase):
    """
    Represents an instance in the database with details like application ID, domain, and state.
    """

    __tablename__ = "instance"  # Table name in the database

    app_id: Mapped[int] = mapped_column(ForeignKey(App.id))

    # Unique domain for each instance
    domain: Mapped[str] = mapped_column(unique=True)

    state: Mapped[InstanceStateEnum] = mapped_column(default=InstanceStateEnum.STOPPED)

    # config_json: Mapped = mapped_column(JSON)
