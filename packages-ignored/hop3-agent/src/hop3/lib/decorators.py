# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from .registry import register

__all__ = ["service", "singleton"]


def service(obj):
    return register(obj, tag="service")


def singleton(obj):
    return register(obj, tag="singleton")
