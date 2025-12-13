# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Basic console output utilities."""

from __future__ import annotations

import sys


def err(*args):
    """Print to stderr."""
    print(*args, file=sys.stderr)


def dim(text: str) -> str:
    """Apply dim ANSI styling to text."""
    return "\x1b[0;37m" + text + "\x1b[0m"
