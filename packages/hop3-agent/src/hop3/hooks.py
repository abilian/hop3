# Copyright (c) 2024-2025, Abilian SAS
from __future__ import annotations

from pluggy import HookimplMarker, HookspecMarker

hookspec = HookspecMarker("hop3")
hookimpl = HookimplMarker("hop3")


@hookspec
def builders():
    """Return a list of hop3 builders."""
