# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 installer testing framework.

This package provides a unified testing framework for Hop3 installers
with support for multiple backends (SSH, Docker, Vagrant).
"""

from __future__ import annotations

from .cli import main
from .common import VERBOSE, Colors, CommandResult, set_verbose
from .runner import TestConfig, TestRunner

__all__ = [
    "Colors",
    "CommandResult",
    "TestConfig",
    "TestRunner",
    "VERBOSE",
    "main",
    "set_verbose",
]
