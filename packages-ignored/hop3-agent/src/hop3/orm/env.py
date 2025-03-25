# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Environment variables for an app.

Note: can be quite lengthy (ARG_MAX=2097152 bytes in recent Linux kernels).
"""

from __future__ import annotations

from advanced_alchemy.base import BigIntBase
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import App


class EnvVar(BigIntBase):
    """Represent an environment variable associated with an instance in the
    database."""

    __tablename__ = "env_var"

    app_id: Mapped[int] = mapped_column(ForeignKey(App.id))
    # Foreign key referencing an app instance in another table

    app: Mapped[App] = relationship(back_populates="env_vars")
    # Relationship to the app instance

    name: Mapped[str]
    # Name of the environment variable

    value: Mapped[str]
    # Value of the environment variable
