# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from typing import TypeVar

from .registry import register

__all__ = ["command", "register"]

T = TypeVar("T")


def command(obj: T) -> T:
    return register(obj, tag="command")
