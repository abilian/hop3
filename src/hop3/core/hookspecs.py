# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import pluggy

hookspec = pluggy.HookspecMarker("hop3")


@hookspec
def cli_commands() -> None:
    """Get CLI commands"""
