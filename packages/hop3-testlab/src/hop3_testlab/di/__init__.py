# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dependency-injection wiring for the Test Lab (Dishka)."""

from __future__ import annotations

from .container import create_async_container

__all__ = ["create_async_container"]
