# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Result storage for hop3-testing.

This module provides:
- SQLAlchemy models for test results
- ResultStore for persisting results to SQLite
- Reporters for output formatting
"""

from __future__ import annotations

# Bundle types are imported INTO results (results -> bundle), never the reverse,
# so bundle.py stays free of any results import (no cycle).
from hop3_testing.bundle import Bundle, ProxyProbe
from hop3_testing.bundle_ids import make_run_id

from .models import TestResultRecord, TestRun, ValidationRecord
from .reporters import ConsoleReporter, narrate_timings
from .store import ResultStore

__all__ = [
    "Bundle",
    "ConsoleReporter",
    "ProxyProbe",
    "ResultStore",
    "TestResultRecord",
    "TestRun",
    "ValidationRecord",
    "make_run_id",
    "narrate_timings",
]
