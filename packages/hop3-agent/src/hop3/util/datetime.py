# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Returns the current time in UTC as a datetime object.

    Returns:
        datetime: The current time in UTC.
    """
    return datetime.now(timezone.utc)
