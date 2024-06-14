# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Environment variables for an app.

Note: can be quite lengthy (ARG_MAX=2097152 bytes in recent Linux kernels).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .app import App
from .base import Base


class EnvVar(Base):
    __tablename__ = "env_vars"

    app_id: Mapped[int] = mapped_column(ForeignKey(App.id))

    name: Mapped[str]
    value: Mapped[str]
