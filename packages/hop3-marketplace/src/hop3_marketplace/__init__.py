# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Static site generator for the public Hop3 app catalog (apps.hop3.cloud)."""

from __future__ import annotations

from .builder import build, main

__all__ = ["build", "main"]
