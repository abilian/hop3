# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)
