# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from datetime import datetime

from advanced_alchemy.types import DateTimeUTC
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

from hop3.util.datetime import utc_now

Base = declarative_base()
metadata = Base.metadata


class TimeStamped:
    """Created At Field Mixin."""

    created_at: Mapped[datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=utc_now,
    )
