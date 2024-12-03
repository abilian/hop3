# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

COMMAND_REGISTRY = {}


def command(cls):
    """Decorator that registers a class as a command by adding it to the
    COMMAND_REGISTRY.

    Input:
    - cls: The class to be registered as a command.

    Returns:
    - cls: The registered class itself, allowing for decorator usage.
    """
    COMMAND_REGISTRY[cls.__name__] = cls
    return cls
