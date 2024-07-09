# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from enum import Enum

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_serializer import SerializerMixin

from hop3.model.app import App


class InstanceStateEnum(Enum):
    RUNNING = 1
    STOPPED = 2
    PAUSED = 3
    # ...


class Instance(BigIntAuditBase, SerializerMixin):
    __tablename__ = "instance"

    app_id: Mapped[int] = mapped_column(ForeignKey(App.id))

    domain: Mapped[str] = mapped_column(unique=True)

    state: Mapped[InstanceStateEnum] = mapped_column(default=InstanceStateEnum.STOPPED)

    # config_json: Mapped = mapped_column(JSON)
