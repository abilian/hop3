# Copyright (c) 2023-2024, Abilian SAS

from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)
