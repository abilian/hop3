# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for hop3.lib.datetime."""

from __future__ import annotations

from datetime import datetime, timezone

from hop3.lib.datetime import utc_now


def test_utc_now_returns_timezone_aware_utc():
    before = datetime.now(timezone.utc)
    now = utc_now()
    after = datetime.now(timezone.utc)

    assert isinstance(now, datetime)
    assert now.tzinfo == timezone.utc
    assert before <= now <= after
