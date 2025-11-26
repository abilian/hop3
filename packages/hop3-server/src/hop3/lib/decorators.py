# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from .registry import register

__all__ = ["command", "register"]


def command(obj):
    return register(obj, tag="command")
