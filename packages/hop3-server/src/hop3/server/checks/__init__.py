# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Support for an app's ``check.py`` smoke test.

Lives in hop3-server rather than the test harness because the server is what
runs these checks: it is present on every box, its venv Python is the
interpreter they execute under, and `hop3 app check` runs them for an app
installed from the catalog — long after any harness has gone. An app's script
therefore imports it directly::

    from hop3.server.checks import run

with nothing to upload and no second copy to drift.
"""

from __future__ import annotations

from ._helper import (
    BROWSER_REQUIRED_MARKER,
    Admin,
    BrowserRequired,
    Check,
    CheckError,
    run,
)

__all__ = [
    "BROWSER_REQUIRED_MARKER",
    "Admin",
    "BrowserRequired",
    "Check",
    "CheckError",
    "run",
]
