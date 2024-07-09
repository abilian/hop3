# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Environment variables for an app.

Note: can be quite lengthy (ARG_MAX=2097152 bytes in recent Linux kernels).
"""

from __future__ import annotations

from advanced_alchemy.base import BigIntPrimaryKey
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .instance import Instance


class EnvVar(BigIntPrimaryKey, Base):
    __tablename__ = "env_var"

    instance_id: Mapped[int] = mapped_column(ForeignKey(Instance.id))

    name: Mapped[str]
    value: Mapped[str]
