# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""User interface components for the Hop3 CLI.

This package handles all user-facing output and input:
- console: Basic console output utilities
- rich_printer: Enhanced printer with Rich formatting
- prompts: Interactive user prompts and confirmations
- messages: User-facing messages (setup instructions, errors, etc.)
"""

from __future__ import annotations

from .console import dim, err
from .messages import show_unauthenticated_message, show_unconfigured_message
from .prompts import confirm, show_destructive_warning, type_to_confirm
from .rich_printer import RichPrinter

__all__ = [
    "RichPrinter",
    "confirm",
    "dim",
    "err",
    "show_destructive_warning",
    "show_unauthenticated_message",
    "show_unconfigured_message",
    "type_to_confirm",
]
