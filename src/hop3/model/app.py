# Copyright (c) 2023-2024, Abilian SAS

from enum import Enum

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_serializer import SerializerMixin


class AppStateEnum(Enum):
    RUNNING = 1
    STOPPED = 2
    PAUSED = 3
    # ...


class App(BigIntAuditBase, SerializerMixin):
    __tablename__ = "apps"

    name: Mapped[str] = mapped_column(String(128))
    run_state: Mapped[AppStateEnum] = mapped_column(default=AppStateEnum.STOPPED)
    port: Mapped[int]
