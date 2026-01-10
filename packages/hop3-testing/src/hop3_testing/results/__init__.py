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

from .models import TestResultRecord, TestRun, ValidationRecord
from .reporters import ConsoleReporter
from .store import ResultStore

__all__ = [
    "ConsoleReporter",
    "ResultStore",
    "TestResultRecord",
    "TestRun",
    "ValidationRecord",
]
