# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from enum import Enum

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class AppStateEnum(Enum):
    """
    Enumeration for representing the state of an application.

    The state of an application can be RUNNING, STOPPED, or PAUSED.
    """

    RUNNING = 1
    STOPPED = 2
    PAUSED = 3
    # ...


class App(BigIntAuditBase):
    """
    Represents an application with relevant properties such as
    name, run state, and port.
    """

    __tablename__ = "app"

    name: Mapped[str] = mapped_column(String(128))
    run_state: Mapped[AppStateEnum] = mapped_column(default=AppStateEnum.STOPPED)
    port: Mapped[int]
    hostanme: Mapped[str]
