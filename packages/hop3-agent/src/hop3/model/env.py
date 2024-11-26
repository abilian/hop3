# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Environment variables for an app.

Note: can be quite lengthy (ARG_MAX=2097152 bytes in recent Linux kernels).
"""

from __future__ import annotations

from advanced_alchemy.base import BigIntPrimaryKey
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base
from .instance import Instance


class EnvVar(BigIntPrimaryKey, Base):
    """
    Represent an environment variable associated with an instance in the database.
    """

    __tablename__ = "env_var"

    instance_id: Mapped[int] = mapped_column(ForeignKey(Instance.id))
    # Foreign key referencing an instance in another table

    name: Mapped[str]
    # Name of the environment variable

    value: Mapped[str]
    # Value of the environment variable
