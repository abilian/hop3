# Copyright (c) 2023-2024, Abilian SAS

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)
