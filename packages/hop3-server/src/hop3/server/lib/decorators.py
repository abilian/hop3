# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from .registry import register

__all__ = ["command", "register", "service"]


def service(obj):
    return register(obj, tag="service")


def singleton(obj):
    return register(obj, tag="singleton")


def command(obj):
    return register(obj, tag="command")
